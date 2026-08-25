from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from langbot.pkg.api.http.service.notification import (
    NotificationIdempotencyConflictError,
    NotificationService,
)
from langbot.pkg.entity.persistence.base import Base
from langbot.pkg.entity.persistence.bot import Bot
from langbot.pkg.entity.persistence.workspace import Workspace
from langbot.pkg.persistence.mgr import PersistenceManager
from langbot.pkg.workspace.errors import WorkspaceNotFoundError


pytestmark = pytest.mark.asyncio

WORKSPACE_A = '00000000-0000-0000-0000-00000000000a'
WORKSPACE_B = '00000000-0000-0000-0000-00000000000b'


@pytest.fixture
async def notification_service(tmp_path):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "notifications.db"}')
    persistence_app = SimpleNamespace()
    persistence_mgr = PersistenceManager(persistence_app)
    persistence_mgr.db = SimpleNamespace(get_engine=lambda: engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            sqlalchemy.insert(Workspace),
            [
                {
                    'uuid': WORKSPACE_A,
                    'instance_uuid': 'instance-a',
                    'name': 'Workspace A',
                    'slug': 'workspace-a',
                    'source': 'cloud_projection',
                },
                {
                    'uuid': WORKSPACE_B,
                    'instance_uuid': 'instance-b',
                    'name': 'Workspace B',
                    'slug': 'workspace-b',
                    'source': 'cloud_projection',
                },
            ],
        )
        await connection.execute(
            sqlalchemy.insert(Bot),
            [
                {
                    'uuid': 'bot-a',
                    'workspace_uuid': WORKSPACE_A,
                    'name': 'Feishu A',
                    'description': 'A',
                    'adapter': 'lark',
                    'adapter_config': {},
                    'enable': True,
                    'pipeline_routing_rules': [],
                },
                {
                    'uuid': 'bot-b',
                    'workspace_uuid': WORKSPACE_B,
                    'name': 'Feishu B',
                    'description': 'B',
                    'adapter': 'lark',
                    'adapter_config': {},
                    'enable': True,
                    'pipeline_routing_rules': [],
                },
            ],
        )

    runtime_a = SimpleNamespace(adapter=SimpleNamespace(send_message=AsyncMock()))
    runtime_b = SimpleNamespace(adapter=SimpleNamespace(send_message=AsyncMock()))

    async def get_runtime_bot(context, bot_uuid):
        workspace_uuid = context if isinstance(context, str) else context.workspace_uuid
        if (workspace_uuid, bot_uuid) == (WORKSPACE_A, 'bot-a'):
            return runtime_a
        if (workspace_uuid, bot_uuid) == (WORKSPACE_B, 'bot-b'):
            return runtime_b
        return None

    application = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        platform_mgr=SimpleNamespace(get_bot_by_uuid=AsyncMock(side_effect=get_runtime_bot)),
    )
    service = NotificationService(application)

    yield service, runtime_a, runtime_b
    await engine.dispose()


async def test_target_crud_is_workspace_scoped(notification_service):
    service, _runtime_a, _runtime_b = notification_service
    created_a = await service.create_target(
        WORKSPACE_A,
        {
            'name': 'On-call group',
            'bot_uuid': 'bot-a',
            'target_type': 'group',
            'target_id': 'chat-a',
            'enabled': True,
        },
    )
    created_b = await service.create_target(
        WORKSPACE_B,
        {
            'name': 'Private alert',
            'bot_uuid': 'bot-b',
            'target_type': 'person',
            'target_id': 'user-b',
            'enabled': True,
        },
    )

    page_a = await service.list_targets(WORKSPACE_A, offset=0, limit=20)
    page_b = await service.list_targets(WORKSPACE_B, offset=0, limit=20)
    assert [target['uuid'] for target in page_a['targets']] == [created_a['uuid']]
    assert [target['uuid'] for target in page_b['targets']] == [created_b['uuid']]
    assert page_a['total'] == 1

    with pytest.raises(WorkspaceNotFoundError):
        await service.update_target(WORKSPACE_A, created_b['uuid'], {'name': 'stolen'})
    with pytest.raises(WorkspaceNotFoundError):
        await service.delete_target(WORKSPACE_A, created_b['uuid'])

    updated = await service.update_target(WORKSPACE_A, created_a['uuid'], {'enabled': False})
    assert updated['enabled'] is False


async def test_send_notification_fans_out_and_idempotent_replay_does_not_resend(notification_service):
    service, runtime_a, _runtime_b = notification_service
    target_person = await service.create_target(
        WORKSPACE_A,
        {
            'name': 'Owner',
            'bot_uuid': 'bot-a',
            'target_type': 'person',
            'target_id': 'user-a',
        },
    )
    target_group = await service.create_target(
        WORKSPACE_A,
        {
            'name': 'Ops group',
            'bot_uuid': 'bot-a',
            'target_type': 'group',
            'target_id': 'chat-a',
        },
    )
    message_chain = [{'type': 'Plain', 'text': 'Service restored'}]

    first = await service.send_notification(
        WORKSPACE_A,
        [target_person['uuid'], target_group['uuid']],
        message_chain,
        'deploy-2026-08-25',
    )
    replay = await service.send_notification(
        WORKSPACE_A,
        [target_person['uuid'], target_group['uuid']],
        message_chain,
        'deploy-2026-08-25',
    )

    assert first['status'] == 'succeeded'
    assert first['replayed'] is False
    assert [item['status'] for item in first['outcomes']] == ['sent', 'sent']
    assert replay['uuid'] == first['uuid']
    assert replay['replayed'] is True
    assert runtime_a.adapter.send_message.await_count == 2


async def test_same_idempotency_key_with_a_different_request_is_rejected(notification_service):
    service, _runtime_a, _runtime_b = notification_service
    target = await service.create_target(
        WORKSPACE_A,
        {
            'name': 'Owner',
            'bot_uuid': 'bot-a',
            'target_type': 'person',
            'target_id': 'user-a',
        },
    )
    await service.send_notification(
        WORKSPACE_A,
        [target['uuid']],
        [{'type': 'Plain', 'text': 'First'}],
        'same-key',
    )

    with pytest.raises(NotificationIdempotencyConflictError):
        await service.send_notification(
            WORKSPACE_A,
            [target['uuid']],
            [{'type': 'Plain', 'text': 'Different'}],
            'same-key',
        )


async def test_partial_failure_is_recorded_per_target(notification_service):
    service, runtime_a, _runtime_b = notification_service
    targets = []
    for name, target_id in [('Good', 'user-good'), ('Bad', 'user-bad')]:
        targets.append(
            await service.create_target(
                WORKSPACE_A,
                {
                    'name': name,
                    'bot_uuid': 'bot-a',
                    'target_type': 'person',
                    'target_id': target_id,
                },
            )
        )

    async def send_message(_target_type, target_id, _message_chain):
        if target_id == 'user-bad':
            raise RuntimeError('platform unavailable')

    runtime_a.adapter.send_message.side_effect = send_message
    result = await service.send_notification(
        WORKSPACE_A,
        [target['uuid'] for target in targets],
        [{'type': 'Plain', 'text': 'Alert'}],
        'partial-send',
    )

    assert result['status'] == 'partial_failed'
    assert [(item['target_id'], item['status']) for item in result['outcomes']] == [
        ('user-good', 'sent'),
        ('user-bad', 'failed'),
    ]
    assert result['outcomes'][1]['error'] == 'platform unavailable'


async def test_send_rejects_disabled_unknown_and_cross_workspace_targets(notification_service):
    service, _runtime_a, _runtime_b = notification_service
    disabled = await service.create_target(
        WORKSPACE_A,
        {
            'name': 'Disabled',
            'bot_uuid': 'bot-a',
            'target_type': 'person',
            'target_id': 'user-disabled',
            'enabled': False,
        },
    )
    other_workspace = await service.create_target(
        WORKSPACE_B,
        {
            'name': 'Other',
            'bot_uuid': 'bot-b',
            'target_type': 'group',
            'target_id': 'chat-b',
        },
    )

    for target_uuid in [disabled['uuid'], other_workspace['uuid'], 'missing']:
        with pytest.raises(WorkspaceNotFoundError):
            await service.send_notification(
                WORKSPACE_A,
                [target_uuid],
                [{'type': 'Plain', 'text': 'Alert'}],
                f'bad-{target_uuid}',
            )
