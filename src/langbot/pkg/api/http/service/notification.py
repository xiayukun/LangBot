from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import sqlalchemy
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ....entity.persistence import bot as persistence_bot
from ....entity.persistence import notification as persistence_notification
from ....workspace.errors import WorkspaceNotFoundError
from .tenant import TenantContext, require_workspace_uuid, scope_statement

if TYPE_CHECKING:
    from ....core import app


class NotificationIdempotencyConflictError(ValueError):
    """The same idempotency key was reused for a different request."""


class NotificationService:
    """Manage reusable destinations and durable, idempotent notification jobs."""

    _MAX_TARGETS_PER_JOB = 100
    _MAX_PAGE_SIZE = 100
    _FANOUT_CONCURRENCY = 8
    _LOCK_STRIPES = 64

    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap
        # Fixed stripes prevent an attacker from growing a lock dictionary with
        # arbitrary idempotency keys. The database unique constraint remains
        # the cross-process source of truth.
        self._idempotency_locks = tuple(asyncio.Lock() for _ in range(self._LOCK_STRIPES))

    async def list_targets(self, context: TenantContext, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        workspace_uuid = require_workspace_uuid(context)
        if not isinstance(offset, int) or offset < 0:
            raise ValueError('offset must be a non-negative integer')
        if not isinstance(limit, int) or limit < 1 or limit > self._MAX_PAGE_SIZE:
            raise ValueError(f'limit must be between 1 and {self._MAX_PAGE_SIZE}')

        count_result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_notification.NotificationTarget),
                persistence_notification.NotificationTarget,
                workspace_uuid,
            )
        )
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_notification.NotificationTarget)
                .order_by(
                    persistence_notification.NotificationTarget.created_at.asc(),
                    persistence_notification.NotificationTarget.uuid.asc(),
                )
                .offset(offset)
                .limit(limit),
                persistence_notification.NotificationTarget,
                workspace_uuid,
            )
        )
        return {
            'targets': [self._serialize_target(row) for row in result.all()],
            'total': int(count_result.scalar_one()),
            'offset': offset,
            'limit': limit,
        }

    async def get_target(self, context: TenantContext, target_uuid: str) -> dict[str, Any] | None:
        row = await self._get_target_row(context, target_uuid)
        return None if row is None else self._serialize_target(row)

    async def create_target(self, context: TenantContext, target_data: dict[str, Any]) -> dict[str, Any]:
        workspace_uuid = require_workspace_uuid(context)
        normalized = self._validate_target_data(target_data, partial=False)
        await self._require_bot(workspace_uuid, normalized['bot_uuid'])
        target_uuid = str(uuid.uuid4())
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_notification.NotificationTarget).values(
                uuid=target_uuid,
                workspace_uuid=workspace_uuid,
                **normalized,
            )
        )
        target = await self.get_target(workspace_uuid, target_uuid)
        if target is None:  # pragma: no cover - database write/read invariant
            raise RuntimeError('Created notification target could not be read back')
        return target

    async def update_target(
        self,
        context: TenantContext,
        target_uuid: str,
        target_data: dict[str, Any],
    ) -> dict[str, Any]:
        workspace_uuid = require_workspace_uuid(context)
        current = await self.get_target(workspace_uuid, target_uuid)
        if current is None:
            raise WorkspaceNotFoundError('Notification target not found')

        updates = self._validate_target_data(target_data, partial=True)
        if not updates:
            return current
        if 'bot_uuid' in updates:
            await self._require_bot(workspace_uuid, updates['bot_uuid'])

        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.update(persistence_notification.NotificationTarget)
                .where(persistence_notification.NotificationTarget.uuid == target_uuid)
                .values(updates),
                persistence_notification.NotificationTarget,
                workspace_uuid,
            )
        )
        if getattr(result, 'rowcount', None) == 0:
            raise WorkspaceNotFoundError('Notification target not found')
        updated = await self.get_target(workspace_uuid, target_uuid)
        if updated is None:  # pragma: no cover - database update/read invariant
            raise RuntimeError('Updated notification target could not be read back')
        return updated

    async def delete_target(self, context: TenantContext, target_uuid: str) -> None:
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.delete(persistence_notification.NotificationTarget).where(
                    persistence_notification.NotificationTarget.uuid == target_uuid
                ),
                persistence_notification.NotificationTarget,
                context,
            )
        )
        if getattr(result, 'rowcount', None) == 0:
            raise WorkspaceNotFoundError('Notification target not found')

    async def send_notification(
        self,
        context: TenantContext,
        target_ids: Sequence[str],
        message_chain: list[dict[str, Any]],
        idempotency_key: str,
    ) -> dict[str, Any]:
        workspace_uuid = require_workspace_uuid(context)
        normalized_target_ids = self._normalize_target_ids(target_ids)
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        normalized_message, runtime_message = self._validate_message_chain(message_chain)
        request_hash = self._request_hash(normalized_target_ids, normalized_message)
        lock = self._idempotency_locks[int(request_hash[:8], 16) % len(self._idempotency_locks)]

        async with lock:
            existing = await self._get_job_by_idempotency_key(workspace_uuid, normalized_key)
            if existing is not None:
                self._require_matching_request(existing, request_hash)
                return await self._serialize_job(workspace_uuid, existing, replayed=True)

            targets = await self._load_enabled_targets(workspace_uuid, normalized_target_ids)
            job_uuid = str(uuid.uuid4())
            created = await self._create_job_if_absent(
                workspace_uuid,
                job_uuid,
                normalized_key,
                request_hash,
                normalized_message,
                targets,
            )
            if not created:
                existing = await self._get_job_by_idempotency_key(workspace_uuid, normalized_key)
                if existing is None:  # pragma: no cover - unique insert invariant
                    raise RuntimeError('Idempotent notification job could not be read back')
                self._require_matching_request(existing, request_hash)
                return await self._serialize_job(workspace_uuid, existing, replayed=True)

            await self._dispatch_and_record(workspace_uuid, job_uuid, targets, runtime_message)
            job = await self._get_job_row(workspace_uuid, job_uuid)
            if job is None:  # pragma: no cover - job lifecycle invariant
                raise RuntimeError('Notification job disappeared during delivery')
            return await self._serialize_job(workspace_uuid, job, replayed=False)

    async def get_job(self, context: TenantContext, job_uuid: str) -> dict[str, Any]:
        workspace_uuid = require_workspace_uuid(context)
        job = await self._get_job_row(workspace_uuid, job_uuid)
        if job is None:
            raise WorkspaceNotFoundError('Notification job not found')
        return await self._serialize_job(workspace_uuid, job, replayed=False)

    async def _require_bot(self, workspace_uuid: str, bot_uuid: str) -> None:
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_bot.Bot.uuid).where(persistence_bot.Bot.uuid == bot_uuid),
                persistence_bot.Bot,
                workspace_uuid,
            )
        )
        if result.first() is None:
            raise WorkspaceNotFoundError('Bot not found')

    async def _get_target_row(self, context: TenantContext, target_uuid: str):
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_notification.NotificationTarget).where(
                    persistence_notification.NotificationTarget.uuid == target_uuid
                ),
                persistence_notification.NotificationTarget,
                context,
            )
        )
        return result.first()

    async def _load_enabled_targets(self, workspace_uuid: str, target_ids: list[str]) -> list[Any]:
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_notification.NotificationTarget).where(
                    persistence_notification.NotificationTarget.uuid.in_(target_ids),
                    persistence_notification.NotificationTarget.enabled.is_(True),
                ),
                persistence_notification.NotificationTarget,
                workspace_uuid,
            )
        )
        by_uuid = {row.uuid: row for row in result.all()}
        if len(by_uuid) != len(target_ids):
            raise WorkspaceNotFoundError('One or more notification targets were not found or are disabled')
        return [by_uuid[target_uuid] for target_uuid in target_ids]

    async def _create_job_if_absent(
        self,
        workspace_uuid: str,
        job_uuid: str,
        idempotency_key: str,
        request_hash: str,
        message_chain: list[dict[str, Any]],
        targets: list[Any],
    ) -> bool:
        dialect_name = self.ap.persistence_mgr.get_db_engine().dialect.name
        values = {
            'uuid': job_uuid,
            'workspace_uuid': workspace_uuid,
            'idempotency_key': idempotency_key,
            'request_hash': request_hash,
            'message_chain': message_chain,
            'status': persistence_notification.JOB_STATUS_PENDING,
        }
        if dialect_name == 'postgresql':
            insert_job = postgres_insert(persistence_notification.NotificationJob).values(values)
        elif dialect_name == 'sqlite':
            insert_job = sqlite_insert(persistence_notification.NotificationJob).values(values)
        else:  # pragma: no cover - LangBot supports SQLite and PostgreSQL
            raise RuntimeError(f'Unsupported notification database dialect: {dialect_name}')
        insert_job = insert_job.on_conflict_do_nothing(
            index_elements=['workspace_uuid', 'idempotency_key']
        )

        async with self.ap.persistence_mgr.tenant_uow(workspace_uuid):
            result = await self.ap.persistence_mgr.execute_async(insert_job)
            if getattr(result, 'rowcount', 0) == 0:
                return False
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_notification.NotificationAttempt),
                [
                    {
                        'uuid': str(uuid.uuid4()),
                        'workspace_uuid': workspace_uuid,
                        'job_uuid': job_uuid,
                        'target_uuid': target.uuid,
                        'position': position,
                        'target_name': target.name,
                        'bot_uuid': target.bot_uuid,
                        'target_type': target.target_type,
                        'target_id': target.target_id,
                        'status': persistence_notification.ATTEMPT_STATUS_PENDING,
                    }
                    for position, target in enumerate(targets)
                ],
            )
        return True

    async def _dispatch_and_record(
        self,
        workspace_uuid: str,
        job_uuid: str,
        targets: list[Any],
        message_chain: Any,
    ) -> None:
        runtime_bots: dict[str, Any] = {}
        for target in targets:
            if target.bot_uuid not in runtime_bots:
                runtime_bots[target.bot_uuid] = await self.ap.platform_mgr.get_bot_by_uuid(
                    workspace_uuid,
                    target.bot_uuid,
                )

        semaphore = asyncio.Semaphore(self._FANOUT_CONCURRENCY)

        async def deliver(target):
            runtime_bot = runtime_bots[target.bot_uuid]
            if runtime_bot is None:
                return persistence_notification.ATTEMPT_STATUS_FAILED, 'Bot is not running'
            try:
                async with semaphore:
                    await runtime_bot.adapter.send_message(target.target_type, str(target.target_id), message_chain)
                return persistence_notification.ATTEMPT_STATUS_SENT, None
            except Exception as exc:
                error = str(exc).strip() or type(exc).__name__
                return persistence_notification.ATTEMPT_STATUS_FAILED, error[:2000]

        results = await asyncio.gather(*(deliver(target) for target in targets))
        sent_count = sum(status == persistence_notification.ATTEMPT_STATUS_SENT for status, _error in results)
        if sent_count == len(results):
            job_status = persistence_notification.JOB_STATUS_SUCCEEDED
        elif sent_count == 0:
            job_status = persistence_notification.JOB_STATUS_FAILED
        else:
            job_status = persistence_notification.JOB_STATUS_PARTIAL_FAILED

        async with self.ap.persistence_mgr.tenant_uow(workspace_uuid):
            for position, (status, error) in enumerate(results):
                await self.ap.persistence_mgr.execute_async(
                    scope_statement(
                        sqlalchemy.update(persistence_notification.NotificationAttempt)
                        .where(
                            persistence_notification.NotificationAttempt.job_uuid == job_uuid,
                            persistence_notification.NotificationAttempt.position == position,
                        )
                        .values(status=status, error=error),
                        persistence_notification.NotificationAttempt,
                        workspace_uuid,
                    )
                )
            await self.ap.persistence_mgr.execute_async(
                scope_statement(
                    sqlalchemy.update(persistence_notification.NotificationJob)
                    .where(persistence_notification.NotificationJob.uuid == job_uuid)
                    .values(status=job_status),
                    persistence_notification.NotificationJob,
                    workspace_uuid,
                )
            )

    async def _get_job_by_idempotency_key(self, workspace_uuid: str, idempotency_key: str):
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_notification.NotificationJob).where(
                    persistence_notification.NotificationJob.idempotency_key == idempotency_key
                ),
                persistence_notification.NotificationJob,
                workspace_uuid,
            )
        )
        return result.first()

    async def _get_job_row(self, workspace_uuid: str, job_uuid: str):
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_notification.NotificationJob).where(
                    persistence_notification.NotificationJob.uuid == job_uuid
                ),
                persistence_notification.NotificationJob,
                workspace_uuid,
            )
        )
        return result.first()

    async def _serialize_job(self, workspace_uuid: str, job: Any, *, replayed: bool) -> dict[str, Any]:
        result = await self.ap.persistence_mgr.execute_async(
            scope_statement(
                sqlalchemy.select(persistence_notification.NotificationAttempt)
                .where(persistence_notification.NotificationAttempt.job_uuid == job.uuid)
                .order_by(persistence_notification.NotificationAttempt.position.asc()),
                persistence_notification.NotificationAttempt,
                workspace_uuid,
            )
        )
        return {
            'uuid': job.uuid,
            'idempotency_key': job.idempotency_key,
            'status': job.status,
            'message_chain': job.message_chain,
            'created_at': self._serialize_datetime(job.created_at),
            'updated_at': self._serialize_datetime(job.updated_at),
            'replayed': replayed,
            'outcomes': [self._serialize_attempt(row) for row in result.all()],
        }

    @staticmethod
    def _serialize_target(row: Any) -> dict[str, Any]:
        return {
            'uuid': row.uuid,
            'name': row.name,
            'bot_uuid': row.bot_uuid,
            'target_type': row.target_type,
            'target_id': row.target_id,
            'enabled': bool(row.enabled),
            'created_at': NotificationService._serialize_datetime(row.created_at),
            'updated_at': NotificationService._serialize_datetime(row.updated_at),
        }

    @staticmethod
    def _serialize_attempt(row: Any) -> dict[str, Any]:
        return {
            'target_uuid': row.target_uuid,
            'target_name': row.target_name,
            'bot_uuid': row.bot_uuid,
            'target_type': row.target_type,
            'target_id': row.target_id,
            'status': row.status,
            'error': row.error,
        }

    @staticmethod
    def _serialize_datetime(value: Any) -> str | None:
        return None if value is None else value.isoformat()

    @staticmethod
    def _validate_target_data(target_data: dict[str, Any], *, partial: bool) -> dict[str, Any]:
        if not isinstance(target_data, dict):
            raise ValueError('target data must be an object')
        allowed = {'name', 'bot_uuid', 'target_type', 'target_id', 'enabled'}
        unknown = set(target_data) - allowed
        if unknown:
            raise ValueError(f'Unsupported notification target fields: {", ".join(sorted(unknown))}')
        required = {'name', 'bot_uuid', 'target_type', 'target_id'}
        if not partial and not required.issubset(target_data):
            missing = ', '.join(sorted(required - set(target_data)))
            raise ValueError(f'Missing notification target fields: {missing}')

        normalized: dict[str, Any] = {}
        for field in ('name', 'bot_uuid', 'target_type', 'target_id'):
            if field not in target_data:
                continue
            value = target_data[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{field} must be a non-empty string')
            normalized[field] = value.strip()
        if 'target_type' in normalized and normalized['target_type'] not in persistence_notification.TARGET_TYPES:
            raise ValueError('target_type must be either "person" or "group"')
        if 'enabled' in target_data:
            if not isinstance(target_data['enabled'], bool):
                raise ValueError('enabled must be a boolean')
            normalized['enabled'] = target_data['enabled']
        elif not partial:
            normalized['enabled'] = True
        return normalized

    def _normalize_target_ids(self, target_ids: Sequence[str]) -> list[str]:
        if isinstance(target_ids, (str, bytes)) or not isinstance(target_ids, Sequence):
            raise ValueError('target_ids must be an array')
        normalized = []
        for target_id in target_ids:
            if not isinstance(target_id, str) or not target_id.strip():
                raise ValueError('Every target ID must be a non-empty string')
            normalized.append(target_id.strip())
        if not normalized:
            raise ValueError('At least one target ID is required')
        if len(normalized) > self._MAX_TARGETS_PER_JOB:
            raise ValueError(f'A notification may contain at most {self._MAX_TARGETS_PER_JOB} targets')
        if len(set(normalized)) != len(normalized):
            raise ValueError('target_ids must not contain duplicates')
        return normalized

    @staticmethod
    def _normalize_idempotency_key(idempotency_key: str) -> str:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError('Idempotency-Key is required')
        normalized = idempotency_key.strip()
        if len(normalized) > 255:
            raise ValueError('Idempotency-Key must not exceed 255 characters')
        return normalized

    @staticmethod
    def _validate_message_chain(message_chain: Any) -> tuple[list[dict[str, Any]], Any]:
        if not isinstance(message_chain, list) or not message_chain:
            raise ValueError('message_chain must be a non-empty array')
        import langbot_plugin.api.entities.builtin.platform.message as platform_message

        try:
            runtime_message = platform_message.MessageChain.model_validate(message_chain)
        except Exception as exc:
            raise ValueError(f'Invalid message_chain: {exc}') from exc
        if any(getattr(component, 'type', None) == 'Unknown' for component in runtime_message):
            raise ValueError('message_chain contains an unsupported component type')
        return runtime_message.model_dump(mode='json'), runtime_message

    @staticmethod
    def _request_hash(target_ids: list[str], message_chain: list[dict[str, Any]]) -> str:
        canonical = json.dumps(
            {'target_ids': target_ids, 'message_chain': message_chain},
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    @staticmethod
    def _require_matching_request(job: Any, request_hash: str) -> None:
        if job.request_hash != request_hash:
            raise NotificationIdempotencyConflictError(
                'Idempotency-Key has already been used for a different notification request'
            )
