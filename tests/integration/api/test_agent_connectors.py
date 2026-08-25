from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from tests.factories import FakeApp


pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def mock_circular_import_chain():
    from tests.utils.import_isolation import MockLifecycleControlScope, isolated_sys_modules

    class FakeMinimalApplication:
        pass

    with isolated_sys_modules(
        mocks={
            'langbot.pkg.core.app': MagicMock(Application=FakeMinimalApplication),
            'langbot.pkg.core.entities': MagicMock(LifecycleControlScope=MockLifecycleControlScope),
        },
        clear=[
            'langbot.pkg.api.http.controller.group',
            'langbot.pkg.api.http.controller.groups',
            'langbot.pkg.api.http.controller.groups.agent_connectors',
            'langbot.pkg.api.http.controller.main',
        ],
    ):
        import langbot.pkg.api.http.controller.groups.agent_connectors as _agent_connectors  # noqa: F401

        yield


@pytest.fixture(scope='module')
def fake_agent_connector_app():
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
                permissions=frozenset({'resource.view', 'resource.manage'}),
            )
        ),
    )
    connector = {
        'uuid': 'connector-test',
        'name': 'Codex bridge',
        'kind': 'codex_bridge',
        'endpoint_url': 'http://127.0.0.1:8765/invoke',
        'system_prompt': 'Help with operations.',
        'skill_names': ['incident-response'],
        'enabled': True,
        'timeout_seconds': 30,
    }
    application.agent_connector_service = Mock(
        list_connectors=AsyncMock(return_value=[connector]),
        list_conversations=AsyncMock(
            return_value=[
                {
                    'uuid': 'conversation-test',
                    'connector_name': 'Codex bridge',
                    'launcher_type': 'person',
                    'launcher_id': 'user-test',
                    'message_count': 2,
                }
            ]
        ),
        get_conversation_history=AsyncMock(
            return_value={
                'conversation': {'uuid': 'conversation-test'},
                'messages': [{'id': 1, 'role': 'user'}],
                'invocations': [{'uuid': 'invocation-test', 'status': 'accepted'}],
            }
        ),
        get_connector=AsyncMock(return_value=connector),
        create_connector=AsyncMock(return_value=connector),
        update_connector=AsyncMock(return_value=connector),
        delete_connector=AsyncMock(),
    )
    return application


@pytest.fixture(scope='module')
async def quart_test_client(fake_agent_connector_app, http_controller_cls):
    controller = http_controller_cls(fake_agent_connector_app)
    await controller.initialize()
    yield controller.quart_app.test_client()


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestAgentConnectorEndpoints:
    @pytest.mark.asyncio
    async def test_list_conversations_and_read_audit_history(self, quart_test_client):
        headers = {'Authorization': 'Bearer user-token'}
        response = await quart_test_client.get('/api/v1/agent-connectors/history/conversations', headers=headers)
        assert response.status_code == 200
        assert (await response.get_json())['data']['conversations'][0]['message_count'] == 2

        response = await quart_test_client.get(
            '/api/v1/agent-connectors/history/conversations/conversation-test', headers=headers
        )
        assert response.status_code == 200
        assert (await response.get_json())['data']['invocations'][0]['status'] == 'accepted'

    @pytest.mark.asyncio
    async def test_list_and_get_connectors(self, quart_test_client):
        headers = {'Authorization': 'Bearer user-token'}
        response = await quart_test_client.get('/api/v1/agent-connectors', headers=headers)
        assert response.status_code == 200
        assert (await response.get_json())['data']['connectors'][0]['uuid'] == 'connector-test'

        response = await quart_test_client.get('/api/v1/agent-connectors/connector-test', headers=headers)
        assert response.status_code == 200
        assert (await response.get_json())['data']['connector']['kind'] == 'codex_bridge'

    @pytest.mark.asyncio
    async def test_create_update_and_delete_connector(self, quart_test_client, fake_agent_connector_app):
        headers = {'Authorization': 'Bearer user-token'}
        body = {
            'name': 'Codex bridge',
            'kind': 'codex_bridge',
            'endpoint_url': 'http://127.0.0.1:8765/invoke',
            'skill_names': ['incident-response'],
        }
        response = await quart_test_client.post('/api/v1/agent-connectors', headers=headers, json=body)
        assert response.status_code == 200
        response = await quart_test_client.put(
            '/api/v1/agent-connectors/connector-test',
            headers=headers,
            json={'enabled': False},
        )
        assert response.status_code == 200
        response = await quart_test_client.delete('/api/v1/agent-connectors/connector-test', headers=headers)
        assert response.status_code == 200
        fake_agent_connector_app.agent_connector_service.delete_connector.assert_awaited()

    @pytest.mark.asyncio
    async def test_validation_error_is_http_400(self, quart_test_client, fake_agent_connector_app):
        fake_agent_connector_app.agent_connector_service.create_connector.side_effect = ValueError('unsafe endpoint')
        try:
            response = await quart_test_client.post(
                '/api/v1/agent-connectors',
                headers={'Authorization': 'Bearer user-token'},
                json={'name': 'Unsafe'},
            )
        finally:
            fake_agent_connector_app.agent_connector_service.create_connector.side_effect = None
        assert response.status_code == 400
