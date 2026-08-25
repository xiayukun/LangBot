from __future__ import annotations

import quart
from sqlalchemy.exc import IntegrityError

from .....workspace.errors import WorkspaceNotFoundError
from ...service.agent_connector import AgentConnectorInUseError
from ...authz import Permission
from ...context import RequestContext
from .. import group


@group.group_class('agent-connectors', '/api/v1/agent-connectors')
class AgentConnectorsRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route(
            '/history/conversations',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(request_context: RequestContext) -> str:
            try:
                limit = int(quart.request.args.get('limit', '100'))
                conversations = await self.ap.agent_connector_service.list_conversations(request_context, limit=limit)
            except (TypeError, ValueError) as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            return self.success(data={'conversations': conversations})

        @self.route(
            '/history/conversations/<conversation_uuid>',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(conversation_uuid: str, request_context: RequestContext) -> str:
            try:
                limit = int(quart.request.args.get('limit', '100'))
                history = await self.ap.agent_connector_service.get_conversation_history(
                    request_context,
                    conversation_uuid,
                    limit=limit,
                )
            except (TypeError, ValueError) as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            except WorkspaceNotFoundError as exc:
                return self.http_status(404, 'resource_not_found', str(exc))
            return self.success(data=history)

        @self.route(
            '',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(request_context: RequestContext) -> str:
            connectors = await self.ap.agent_connector_service.list_connectors(request_context)
            return self.success(data={'connectors': connectors})

        @self.route(
            '',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_MANAGE,
        )
        async def _(request_context: RequestContext) -> str:
            data = await quart.request.get_json()
            if not isinstance(data, dict):
                return self.http_status(400, 'invalid_request', 'Request body must be a JSON object')
            try:
                connector = await self.ap.agent_connector_service.create_connector(request_context, data)
            except ValueError as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            except IntegrityError:
                return self.http_status(409, 'connector_already_exists', 'Agent connector name already exists')
            return self.success(data={'connector': connector})

        @self.route(
            '/<connector_uuid>',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_VIEW,
        )
        async def _(connector_uuid: str, request_context: RequestContext) -> str:
            connector = await self.ap.agent_connector_service.get_connector(request_context, connector_uuid)
            if connector is None:
                return self.http_status(404, 'resource_not_found', 'Agent connector not found')
            return self.success(data={'connector': connector})

        @self.route(
            '/<connector_uuid>',
            methods=['PUT'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_MANAGE,
        )
        async def _(connector_uuid: str, request_context: RequestContext) -> str:
            data = await quart.request.get_json()
            if not isinstance(data, dict):
                return self.http_status(400, 'invalid_request', 'Request body must be a JSON object')
            try:
                connector = await self.ap.agent_connector_service.update_connector(
                    request_context,
                    connector_uuid,
                    data,
                )
            except ValueError as exc:
                return self.http_status(400, 'invalid_request', str(exc))
            except IntegrityError:
                return self.http_status(409, 'connector_already_exists', 'Agent connector name already exists')
            return self.success(data={'connector': connector})

        @self.route(
            '/<connector_uuid>',
            methods=['DELETE'],
            auth_type=group.AuthType.USER_TOKEN_OR_API_KEY,
            permission=Permission.RESOURCE_MANAGE,
        )
        async def _(connector_uuid: str, request_context: RequestContext) -> str:
            try:
                await self.ap.agent_connector_service.delete_connector(request_context, connector_uuid)
            except AgentConnectorInUseError as exc:
                return self.http_status(409, 'connector_in_use', str(exc))
            return self.success()
