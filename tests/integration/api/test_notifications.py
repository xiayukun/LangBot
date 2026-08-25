from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, Mock

import pytest

from langbot.pkg.api.http.service.notification import NotificationIdempotencyConflictError
from tests.factories import FakeApp


pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def mock_circular_import_chain():
    from tests.utils.import_isolation import MockLifecycleControlScope, isolated_sys_modules

    class FakeMinimalApplication:
        pass

    mock_app = MagicMock(Application=FakeMinimalApplication)
    mock_entities = MagicMock(LifecycleControlScope=MockLifecycleControlScope)
    clear = [
        'langbot.pkg.api.http.controller.group',
        'langbot.pkg.api.http.controller.groups',
        'langbot.pkg.api.http.controller.groups.notifications',
        'langbot.pkg.api.http.controller.main',
    ]
    with isolated_sys_modules(
        mocks={
            'langbot.pkg.core.app': mock_app,
            'langbot.pkg.core.entities': mock_entities,
        },
        clear=clear,
    ):
        import langbot.pkg.api.http.controller.groups.notifications as _notifications  # noqa: F401

        yield


@pytest.fixture(scope='module')
def fake_notification_app():
    application = FakeApp()
    application.instance_config.data.update(
        {
            'api': {'port': 5300},
            'system': {'allow_modify_login_info': True, 'limitation': {}},
        }
    )
    account = SimpleNamespace(uuid='account-test', user='test@example.com')
    application.user_service = Mock(
        verify_jwt_token=AsyncMock(return_value='test@example.com'),
        get_user_by_email=AsyncMock(return_value=account),
        get_authenticated_account=AsyncMock(return_value=account),
    )
    application.workspace_collaboration_service = SimpleNamespace(
        resolve_account_workspace=AsyncMock(
            return_value=SimpleNamespace(
                workspace=SimpleNamespace(uuid='workspace-test'),
                membership=SimpleNamespace(uuid='membership-test', role='owner', projection_revision=0),
                execution=SimpleNamespace(instance_uuid='instance-test', placement_generation=1),
            )
        )
    )
    application.apikey_service = Mock(
        verify_api_key=AsyncMock(return_value=True),
        authenticate_api_key=AsyncMock(
            return_value=SimpleNamespace(
                instance_uuid='instance-test',
                placement_generation=1,
                api_key_uuid='api-key-test',
                workspace_uuid='workspace-test',
                permissions=frozenset({'resource.view', 'resource.manage', 'runtime.operate'}),
            )
        ),
    )
    target = {
        'uuid': 'target-test',
        'name': 'Ops',
        'bot_uuid': 'bot-test',
        'target_type': 'group',
        'target_id': 'chat-test',
        'enabled': True,
    }
    job = {
        'uuid': 'job-test',
        'idempotency_key': 'request-test',
        'status': 'succeeded',
        'replayed': False,
        'outcomes': [{'target_uuid': 'target-test', 'status': 'sent'}],
    }
    application.notification_service = Mock(
        list_targets=AsyncMock(return_value={'targets': [target], 'total': 1, 'offset': 0, 'limit': 50}),
        get_target=AsyncMock(return_value=target),
        create_target=AsyncMock(return_value=target),
        update_target=AsyncMock(return_value=target),
        delete_target=AsyncMock(),
        send_notification=AsyncMock(return_value=job),
        get_job=AsyncMock(return_value=job),
    )
    return application


@pytest.fixture(scope='module')
async def quart_test_client(fake_notification_app, http_controller_cls):
    controller = http_controller_cls(fake_notification_app)
    await controller.initialize()
    yield controller.quart_app.test_client()


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestNotificationEndpoints:
    @pytest.mark.asyncio
    async def test_target_crud_and_pagination(self, quart_test_client, fake_notification_app):
        headers = {'Authorization': 'Bearer user-token'}
        response = await quart_test_client.get('/api/v1/notification-targets?offset=0&limit=50', headers=headers)
        assert response.status_code == 200
        assert (await response.get_json())['data']['total'] == 1

        response = await quart_test_client.post(
            '/api/v1/notification-targets',
            headers=headers,
            json={
                'name': 'Ops',
                'bot_uuid': 'bot-test',
                'target_type': 'group',
                'target_id': 'chat-test',
            },
        )
        assert response.status_code == 200
        assert (await response.get_json())['data']['target']['uuid'] == 'target-test'

        response = await quart_test_client.put(
            '/api/v1/notification-targets/target-test',
            headers=headers,
            json={'enabled': False},
        )
        assert response.status_code == 200
        response = await quart_test_client.delete('/api/v1/notification-targets/target-test', headers=headers)
        assert response.status_code == 200
        fake_notification_app.notification_service.delete_target.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_uses_idempotency_header_and_camel_case_body(
        self,
        quart_test_client,
        fake_notification_app,
    ):
        response = await quart_test_client.post(
            '/api/v1/notifications',
            headers={'X-API-Key': 'api-key', 'Idempotency-Key': 'request-test'},
            json={
                'targetIds': ['target-test'],
                'messageChain': [{'type': 'Plain', 'text': 'Service restored'}],
            },
        )
        assert response.status_code == 200
        assert (await response.get_json())['data']['job']['status'] == 'succeeded'
        fake_notification_app.notification_service.send_notification.assert_awaited_with(
            ANY,
            ['target-test'],
            [{'type': 'Plain', 'text': 'Service restored'}],
            'request-test',
        )

    @pytest.mark.asyncio
    async def test_send_requires_idempotency_key(self, quart_test_client):
        response = await quart_test_client.post(
            '/api/v1/notifications',
            headers={'X-API-Key': 'api-key'},
            json={'targetIds': ['target-test'], 'messageChain': [{'type': 'Plain', 'text': 'Hello'}]},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_idempotency_conflict_is_http_409(
        self,
        quart_test_client,
        fake_notification_app,
    ):
        fake_notification_app.notification_service.send_notification.side_effect = (
            NotificationIdempotencyConflictError('different request')
        )
        try:
            response = await quart_test_client.post(
                '/api/v1/notifications',
                headers={'X-API-Key': 'api-key', 'Idempotency-Key': 'duplicate'},
                json={'targetIds': ['target-test'], 'messageChain': [{'type': 'Plain', 'text': 'Hello'}]},
            )
        finally:
            fake_notification_app.notification_service.send_notification.side_effect = None
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_get_job(self, quart_test_client):
        response = await quart_test_client.get(
            '/api/v1/notifications/job-test',
            headers={'X-API-Key': 'api-key'},
        )
        assert response.status_code == 200
        assert (await response.get_json())['data']['job']['uuid'] == 'job-test'
