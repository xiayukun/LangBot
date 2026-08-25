from __future__ import annotations

import quart
from sqlalchemy.exc import IntegrityError

from ...authz import Permission
from ...context import RequestContext
from ...service.notification import NotificationIdempotencyConflictError
from .. import group


@group.group_class('notification-targets', '/api/v1/notification-targets')
class NotificationTargetsRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route(
            '',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(request_context: RequestContext) -> str:
            try:
                offset = int(quart.request.args.get('offset', '0'))
                limit = int(quart.request.args.get('limit', '50'))
                page = await self.ap.notification_service.list_targets(
                    request_context,
                    offset=offset,
                    limit=limit,
                )
            except ValueError as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            return self.success(data=page)

        @self.route(
            '',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_MANAGE,
        )
        async def _(request_context: RequestContext) -> str:
            json_data = await quart.request.get_json()
            if not isinstance(json_data, dict):
                return self.http_status(400, 'invalid_request', 'Request body must be a JSON object')
            try:
                target = await self.ap.notification_service.create_target(request_context, json_data)
            except ValueError as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            except IntegrityError:
                return self.http_status(409, 'target_already_exists', 'Notification target already exists')
            return self.success(data={'target': target})

        @self.route(
            '/<target_uuid>',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(target_uuid: str, request_context: RequestContext) -> str:
            target = await self.ap.notification_service.get_target(request_context, target_uuid)
            if target is None:
                return self.http_status(404, 'resource_not_found', 'Notification target not found')
            return self.success(data={'target': target})

        @self.route(
            '/<target_uuid>',
            methods=['PUT'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_MANAGE,
        )
        async def _(target_uuid: str, request_context: RequestContext) -> str:
            json_data = await quart.request.get_json()
            if not isinstance(json_data, dict):
                return self.http_status(400, 'invalid_request', 'Request body must be a JSON object')
            try:
                target = await self.ap.notification_service.update_target(
                    request_context,
                    target_uuid,
                    json_data,
                )
            except ValueError as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            except IntegrityError:
                return self.http_status(409, 'target_already_exists', 'Notification target already exists')
            return self.success(data={'target': target})

        @self.route(
            '/<target_uuid>',
            methods=['DELETE'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_MANAGE,
        )
        async def _(target_uuid: str, request_context: RequestContext) -> str:
            await self.ap.notification_service.delete_target(request_context, target_uuid)
            return self.success()


@group.group_class('notifications', '/api/v1/notifications')
class NotificationsRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route(
            '',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RUNTIME_OPERATE,
        )
        async def _(request_context: RequestContext) -> str:
            json_data = await quart.request.get_json()
            if not isinstance(json_data, dict):
                return self.http_status(400, 'invalid_request', 'Request body must be a JSON object')

            idempotency_key = quart.request.headers.get('Idempotency-Key', '')
            if not idempotency_key.strip():
                return self.http_status(400, 'idempotency_key_required', 'Idempotency-Key header is required')
            target_ids = json_data.get('targetIds', json_data.get('target_ids'))
            message_chain = json_data.get('messageChain', json_data.get('message_chain'))
            try:
                job = await self.ap.notification_service.send_notification(
                    request_context,
                    target_ids,
                    message_chain,
                    idempotency_key,
                )
            except NotificationIdempotencyConflictError as exc:
                return self.http_status(409, 'idempotency_conflict', str(exc))
            except ValueError as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            return self.success(data={'job': job})

        @self.route(
            '/<job_uuid>',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(job_uuid: str, request_context: RequestContext) -> str:
            job = await self.ap.notification_service.get_job(request_context, job_uuid)
            return self.success(data={'job': job})
