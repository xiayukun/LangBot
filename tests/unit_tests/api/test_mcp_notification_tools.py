from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from langbot.pkg.api.http.authz import Permission
from langbot.pkg.api.http.context import PrincipalContext, PrincipalType, RequestContext, WorkspaceContext
from langbot.pkg.api.mcp.context import bind_request_context, reset_request_context
from langbot.pkg.api.mcp.server import INSTRUCTIONS, LangBotMCPServer


def _request_context(*permissions: Permission) -> RequestContext:
    return RequestContext(
        instance_uuid='instance-test',
        placement_generation=1,
        request_id='request-test',
        auth_type='api-key',
        principal=PrincipalContext(
            principal_type=PrincipalType.API_KEY,
            api_key_uuid='key-test',
        ),
        workspace=WorkspaceContext(
            workspace_uuid='workspace-test',
            membership_uuid=None,
            role=None,
            permissions=frozenset(permission.value for permission in permissions),
        ),
    )


def _application() -> SimpleNamespace:
    return SimpleNamespace(
        bot_service=SimpleNamespace(send_message=AsyncMock()),
        notification_service=SimpleNamespace(
            list_targets=AsyncMock(
                return_value={
                    'targets': [{'uuid': 'target-test', 'name': 'Ops group'}],
                    'total': 1,
                    'offset': 0,
                    'limit': 50,
                }
            ),
            send_notification=AsyncMock(
                return_value={
                    'uuid': 'job-test',
                    'status': 'succeeded',
                    'replayed': False,
                    'outcomes': [{'target_uuid': 'target-test', 'status': 'sent'}],
                }
            ),
            get_job=AsyncMock(return_value={'uuid': 'job-test', 'status': 'succeeded'}),
        ),
    )


def test_server_instructions_explain_the_safe_notification_workflow() -> None:
    assert 'send_notification' in INSTRUCTIONS
    assert 'list_notification_targets' in INSTRUCTIONS
    assert 'Never guess' in INSTRUCTIONS


@pytest.mark.asyncio
async def test_managed_notification_tools_are_discoverable_and_delegate_to_service() -> None:
    application = _application()
    server = LangBotMCPServer(application)
    context = _request_context(Permission.RESOURCE_VIEW, Permission.RUNTIME_OPERATE)
    tools = await server.mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert {'list_notification_targets', 'send_notification', 'get_notification_job'} <= tool_names

    token = bind_request_context(context)
    try:
        list_result = await server.mcp.call_tool(
            'list_notification_targets',
            {'offset': 0, 'limit': 50},
        )
        send_result = await server.mcp.call_tool(
            'send_notification',
            {
                'target_ids': ['target-test'],
                'message_chain': [{'type': 'Plain', 'text': 'Service restored'}],
                'idempotency_key': 'deploy-2026-08-25',
            },
        )
        get_result = await server.mcp.call_tool(
            'get_notification_job',
            {'job_uuid': 'job-test'},
        )
    finally:
        reset_request_context(token)

    application.notification_service.list_targets.assert_awaited_once_with(context, offset=0, limit=50)
    application.notification_service.send_notification.assert_awaited_once_with(
        context,
        ['target-test'],
        [{'type': 'Plain', 'text': 'Service restored'}],
        'deploy-2026-08-25',
    )
    application.notification_service.get_job.assert_awaited_once_with(context, 'job-test')
    assert json.loads(list_result[0][0].text)['total'] == 1
    assert json.loads(send_result[0][0].text)['uuid'] == 'job-test'
    assert json.loads(get_result[0][0].text)['status'] == 'succeeded'


@pytest.mark.asyncio
async def test_send_message_tool_is_discoverable_and_sends_through_bot_service() -> None:
    application = _application()
    server = LangBotMCPServer(application)
    context = _request_context(Permission.RUNTIME_OPERATE)
    message_chain = [{'type': 'text', 'text': 'Service restored'}]

    tools = await server.mcp.list_tools()
    assert 'send_message' in {tool.name for tool in tools}

    token = bind_request_context(context)
    try:
        result = await server.mcp.call_tool(
            'send_message',
            {
                'bot_uuid': 'bot-test',
                'target_type': 'group',
                'target_id': 'chat-test',
                'message_chain': message_chain,
            },
        )
    finally:
        reset_request_context(token)

    application.bot_service.send_message.assert_awaited_once_with(
        context,
        'bot-test',
        'group',
        'chat-test',
        message_chain,
    )
    content, _structured_result = result
    payload = json.loads(content[0].text)
    assert payload == {
        'sent': True,
        'bot_uuid': 'bot-test',
        'target_type': 'group',
        'target_id': 'chat-test',
    }


@pytest.mark.asyncio
async def test_send_message_tool_requires_runtime_operate_permission() -> None:
    application = _application()
    server = LangBotMCPServer(application)
    token = bind_request_context(_request_context(Permission.RESOURCE_VIEW))

    try:
        with pytest.raises(ToolError, match=Permission.RUNTIME_OPERATE.value):
            await server.mcp.call_tool(
                'send_message',
                {
                    'bot_uuid': 'bot-test',
                    'target_type': 'person',
                    'target_id': 'user-test',
                    'message_chain': [{'type': 'text', 'text': 'Hello'}],
                },
            )
    finally:
        reset_request_context(token)

    application.bot_service.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_message_tool_rejects_an_unsupported_target_type() -> None:
    application = _application()
    server = LangBotMCPServer(application)
    token = bind_request_context(_request_context(Permission.RUNTIME_OPERATE))

    try:
        with pytest.raises(ToolError, match='target_type'):
            await server.mcp.call_tool(
                'send_message',
                {
                    'bot_uuid': 'bot-test',
                    'target_type': 'channel',
                    'target_id': 'target-test',
                    'message_chain': [{'type': 'text', 'text': 'Hello'}],
                },
            )
    finally:
        reset_request_context(token)

    application.bot_service.send_message.assert_not_awaited()
