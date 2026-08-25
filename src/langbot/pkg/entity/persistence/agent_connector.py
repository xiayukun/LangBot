from __future__ import annotations

import sqlalchemy

from .base import Base


CONNECTOR_KINDS = frozenset({'http', 'codex_bridge'})
MESSAGE_ROLES = frozenset({'user', 'assistant'})

INVOCATION_PENDING = 'pending'
INVOCATION_ACCEPTED = 'accepted'
INVOCATION_REJECTED = 'rejected'
INVOCATION_FAILED = 'failed'
INVOCATION_REPLY_FAILED = 'reply_failed'


class AgentConnector(Base):
    """A configured external Agent endpoint without embedded credentials."""

    __tablename__ = 'agent_connectors'

    uuid = sqlalchemy.Column(sqlalchemy.String(36), primary_key=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    kind = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    endpoint_url = sqlalchemy.Column(sqlalchemy.String(2048), nullable=False)
    system_prompt = sqlalchemy.Column(sqlalchemy.Text, nullable=False, default='', server_default='')
    skill_names = sqlalchemy.Column(sqlalchemy.JSON, nullable=False, default=list, server_default='[]')
    enabled = sqlalchemy.Column(
        sqlalchemy.Boolean,
        nullable=False,
        default=True,
        server_default=sqlalchemy.true(),
    )
    timeout_seconds = sqlalchemy.Column(
        sqlalchemy.Integer,
        nullable=False,
        default=30,
        server_default='30',
    )
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )

    __table_args__ = (
        sqlalchemy.CheckConstraint("kind IN ('http', 'codex_bridge')", name='ck_agent_connectors_kind'),
        sqlalchemy.CheckConstraint(
            'timeout_seconds BETWEEN 1 AND 120',
            name='ck_agent_connectors_timeout',
        ),
        sqlalchemy.UniqueConstraint('workspace_uuid', 'name', name='uq_agent_connectors_workspace_name'),
        sqlalchemy.UniqueConstraint('workspace_uuid', 'uuid', name='uq_agent_connectors_workspace_uuid'),
    )


class AgentConversation(Base):
    """A stable chat identity scoped to one connector and platform launcher."""

    __tablename__ = 'agent_conversations'

    uuid = sqlalchemy.Column(sqlalchemy.String(36), primary_key=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    connector_uuid = sqlalchemy.Column(sqlalchemy.String(36), nullable=False)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    launcher_type = sqlalchemy.Column(sqlalchemy.String(16), nullable=False)
    launcher_id = sqlalchemy.Column(sqlalchemy.String(512), nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )

    __table_args__ = (
        sqlalchemy.ForeignKeyConstraint(
            ['workspace_uuid', 'connector_uuid'],
            ['agent_connectors.workspace_uuid', 'agent_connectors.uuid'],
            name='fk_agent_conversations_workspace_connector',
            ondelete='CASCADE',
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['workspace_uuid', 'bot_uuid'],
            ['bots.workspace_uuid', 'bots.uuid'],
            name='fk_agent_conversations_workspace_bot',
            ondelete='CASCADE',
        ),
        sqlalchemy.CheckConstraint(
            "launcher_type IN ('person', 'group')",
            name='ck_agent_conversations_launcher_type',
        ),
        sqlalchemy.UniqueConstraint(
            'workspace_uuid',
            'connector_uuid',
            'bot_uuid',
            'launcher_type',
            'launcher_id',
            name='uq_agent_conversations_route',
        ),
        sqlalchemy.UniqueConstraint('workspace_uuid', 'uuid', name='uq_agent_conversations_workspace_uuid'),
    )


class AgentMessage(Base):
    """An ordered durable transcript message supplied to an Agent connector."""

    __tablename__ = 'agent_messages'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    conversation_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('agent_conversations.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    role = sqlalchemy.Column(sqlalchemy.String(16), nullable=False)
    sender_id = sqlalchemy.Column(sqlalchemy.String(512), nullable=True)
    source_event_id = sqlalchemy.Column(sqlalchemy.String(512), nullable=True)
    message_chain = sqlalchemy.Column(sqlalchemy.JSON, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())

    __table_args__ = (
        sqlalchemy.CheckConstraint("role IN ('user', 'assistant')", name='ck_agent_messages_role'),
        sqlalchemy.UniqueConstraint(
            'workspace_uuid',
            'conversation_uuid',
            'source_event_id',
            name='uq_agent_messages_source_event',
        ),
        sqlalchemy.Index('ix_agent_messages_workspace_conversation', 'workspace_uuid', 'conversation_uuid', 'id'),
    )


class AgentCursor(Base):
    """The last transcript message accepted by the Agent for a conversation."""

    __tablename__ = 'agent_cursors'

    conversation_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('agent_conversations.uuid', ondelete='CASCADE'),
        primary_key=True,
    )
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    last_message_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('agent_messages.id', ondelete='SET NULL'),
        nullable=True,
    )
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )

    __table_args__ = (sqlalchemy.Index('ix_agent_cursors_workspace', 'workspace_uuid'),)


class AgentInvocation(Base):
    """An idempotent, auditable attempt to deliver unseen context to an Agent."""

    __tablename__ = 'agent_invocations'

    uuid = sqlalchemy.Column(sqlalchemy.String(36), primary_key=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    conversation_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('agent_conversations.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    through_message_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('agent_messages.id', ondelete='CASCADE'),
        nullable=False,
    )
    reply_message_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('agent_messages.id', ondelete='SET NULL'),
        nullable=True,
    )
    status = sqlalchemy.Column(
        sqlalchemy.String(32),
        nullable=False,
        default=INVOCATION_PENDING,
        server_default=sqlalchemy.text("'pending'"),
    )
    error = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )

    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'workspace_uuid',
            'conversation_uuid',
            'through_message_id',
            name='uq_agent_invocations_message',
        ),
        sqlalchemy.Index('ix_agent_invocations_workspace_conversation', 'workspace_uuid', 'conversation_uuid'),
    )
