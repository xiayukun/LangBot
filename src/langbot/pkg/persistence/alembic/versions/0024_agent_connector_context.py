"""add durable Agent connector context

Revision ID: 0024_agent_connector_context
Revises: 0023_notification_gateway
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '0024_agent_connector_context'
down_revision = '0023_notification_gateway'
branch_labels = None
depends_on = None


_TABLES = (
    'agent_connectors',
    'agent_conversations',
    'agent_messages',
    'agent_cursors',
    'agent_invocations',
)
_POLICY_NAME = 'langbot_workspace_isolation'
_TENANT_SETTING = 'langbot.workspace_uuid'


def _quote(conn: sa.Connection, identifier: str) -> str:
    return conn.dialect.identifier_preparer.quote(identifier)


def _install_tenant_policy(conn: sa.Connection, table_name: str) -> None:
    if conn.dialect.name != 'postgresql':
        return
    table = _quote(conn, table_name)
    policy = _quote(conn, _POLICY_NAME)
    expression = f"workspace_uuid::text = NULLIF(current_setting('{_TENANT_SETTING}', true), '')"
    op.execute(sa.text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON {table}'))
    op.execute(
        sa.text(
            f'CREATE POLICY {policy} ON {table} AS PERMISSIVE FOR ALL TO PUBLIC '
            f'USING ({expression}) WITH CHECK ({expression})'
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())

    if 'agent_connectors' not in existing:
        op.create_table(
            'agent_connectors',
            sa.Column('uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('kind', sa.String(32), nullable=False),
            sa.Column('endpoint_url', sa.String(2048), nullable=False),
            sa.Column('system_prompt', sa.Text(), server_default='', nullable=False),
            sa.Column('skill_names', sa.JSON(), server_default='[]', nullable=False),
            sa.Column('enabled', sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column('timeout_seconds', sa.Integer(), server_default='30', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("kind IN ('http', 'codex_bridge')", name='ck_agent_connectors_kind'),
            sa.CheckConstraint('timeout_seconds BETWEEN 1 AND 120', name='ck_agent_connectors_timeout'),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('uuid'),
            sa.UniqueConstraint('workspace_uuid', 'name', name='uq_agent_connectors_workspace_name'),
            sa.UniqueConstraint('workspace_uuid', 'uuid', name='uq_agent_connectors_workspace_uuid'),
        )

    if 'agent_conversations' not in existing:
        op.create_table(
            'agent_conversations',
            sa.Column('uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('connector_uuid', sa.String(36), nullable=False),
            sa.Column('bot_uuid', sa.String(255), nullable=False),
            sa.Column('launcher_type', sa.String(16), nullable=False),
            sa.Column('launcher_id', sa.String(512), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "launcher_type IN ('person', 'group')",
                name='ck_agent_conversations_launcher_type',
            ),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(
                ['workspace_uuid', 'connector_uuid'],
                ['agent_connectors.workspace_uuid', 'agent_connectors.uuid'],
                name='fk_agent_conversations_workspace_connector',
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['workspace_uuid', 'bot_uuid'],
                ['bots.workspace_uuid', 'bots.uuid'],
                name='fk_agent_conversations_workspace_bot',
                ondelete='CASCADE',
            ),
            sa.PrimaryKeyConstraint('uuid'),
            sa.UniqueConstraint(
                'workspace_uuid',
                'connector_uuid',
                'bot_uuid',
                'launcher_type',
                'launcher_id',
                name='uq_agent_conversations_route',
            ),
            sa.UniqueConstraint('workspace_uuid', 'uuid', name='uq_agent_conversations_workspace_uuid'),
        )

    if 'agent_messages' not in existing:
        op.create_table(
            'agent_messages',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('conversation_uuid', sa.String(36), nullable=False),
            sa.Column('role', sa.String(16), nullable=False),
            sa.Column('sender_id', sa.String(512), nullable=True),
            sa.Column('source_event_id', sa.String(512), nullable=True),
            sa.Column('message_chain', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_agent_messages_role'),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['conversation_uuid'], ['agent_conversations.uuid'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'workspace_uuid',
                'conversation_uuid',
                'source_event_id',
                name='uq_agent_messages_source_event',
            ),
        )
        op.create_index(
            'ix_agent_messages_workspace_conversation',
            'agent_messages',
            ['workspace_uuid', 'conversation_uuid', 'id'],
            unique=False,
        )

    if 'agent_cursors' not in existing:
        op.create_table(
            'agent_cursors',
            sa.Column('conversation_uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('last_message_id', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['conversation_uuid'], ['agent_conversations.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['last_message_id'], ['agent_messages.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('conversation_uuid'),
        )
        op.create_index('ix_agent_cursors_workspace', 'agent_cursors', ['workspace_uuid'], unique=False)

    if 'agent_invocations' not in existing:
        op.create_table(
            'agent_invocations',
            sa.Column('uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('conversation_uuid', sa.String(36), nullable=False),
            sa.Column('through_message_id', sa.Integer(), nullable=False),
            sa.Column('reply_message_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(32), server_default=sa.text("'pending'"), nullable=False),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['conversation_uuid'], ['agent_conversations.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['reply_message_id'], ['agent_messages.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['through_message_id'], ['agent_messages.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('uuid'),
            sa.UniqueConstraint(
                'workspace_uuid',
                'conversation_uuid',
                'through_message_id',
                name='uq_agent_invocations_message',
            ),
        )
        op.create_index(
            'ix_agent_invocations_workspace_conversation',
            'agent_invocations',
            ['workspace_uuid', 'conversation_uuid'],
            unique=False,
        )

    created_tables = set(sa.inspect(conn).get_table_names())
    for table_name in _TABLES:
        if table_name in created_tables:
            _install_tenant_policy(conn, table_name)


def downgrade() -> None:
    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())
    for table_name in reversed(_TABLES):
        if table_name not in existing:
            continue
        if conn.dialect.name == 'postgresql':
            table = _quote(conn, table_name)
            policy = _quote(conn, _POLICY_NAME)
            op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON {table}'))
        op.drop_table(table_name)
