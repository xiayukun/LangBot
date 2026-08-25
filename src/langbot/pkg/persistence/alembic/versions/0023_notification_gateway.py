"""add managed notification targets and delivery jobs

Revision ID: 0023_notification_gateway
Revises: 0022_bot_routing_mode
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '0023_notification_gateway'
down_revision = '0022_bot_routing_mode'
branch_labels = None
depends_on = None


_TABLES = ('notification_targets', 'notification_jobs', 'notification_attempts')
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
    existing_tables = set(sa.inspect(conn).get_table_names())

    if 'notification_targets' not in existing_tables:
        op.create_table(
            'notification_targets',
            sa.Column('uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('bot_uuid', sa.String(255), nullable=False),
            sa.Column('target_type', sa.String(16), nullable=False),
            sa.Column('target_id', sa.String(512), nullable=False),
            sa.Column('enabled', sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("target_type IN ('person', 'group')", name='ck_notification_targets_type'),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(
                ['workspace_uuid', 'bot_uuid'],
                ['bots.workspace_uuid', 'bots.uuid'],
                name='fk_notification_targets_workspace_bot',
                ondelete='CASCADE',
            ),
            sa.PrimaryKeyConstraint('uuid'),
            sa.UniqueConstraint(
                'workspace_uuid',
                'bot_uuid',
                'target_type',
                'target_id',
                name='uq_notification_targets_destination',
            ),
        )
        op.create_index(
            'ix_notification_targets_workspace_name',
            'notification_targets',
            ['workspace_uuid', 'name'],
            unique=False,
        )

    if 'notification_jobs' not in existing_tables:
        op.create_table(
            'notification_jobs',
            sa.Column('uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('idempotency_key', sa.String(255), nullable=False),
            sa.Column('request_hash', sa.String(64), nullable=False),
            sa.Column('message_chain', sa.JSON(), nullable=False),
            sa.Column('status', sa.String(32), server_default=sa.text("'pending'"), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('uuid'),
            sa.UniqueConstraint(
                'workspace_uuid',
                'idempotency_key',
                name='uq_notification_jobs_idempotency',
            ),
        )
        op.create_index(
            'ix_notification_jobs_workspace_created',
            'notification_jobs',
            ['workspace_uuid', 'created_at'],
            unique=False,
        )

    if 'notification_attempts' not in existing_tables:
        op.create_table(
            'notification_attempts',
            sa.Column('uuid', sa.String(36), nullable=False),
            sa.Column('workspace_uuid', sa.String(36), nullable=False),
            sa.Column('job_uuid', sa.String(36), nullable=False),
            sa.Column('target_uuid', sa.String(36), nullable=True),
            sa.Column('position', sa.Integer(), nullable=False),
            sa.Column('target_name', sa.String(255), nullable=False),
            sa.Column('bot_uuid', sa.String(255), nullable=False),
            sa.Column('target_type', sa.String(16), nullable=False),
            sa.Column('target_id', sa.String(512), nullable=False),
            sa.Column('status', sa.String(32), server_default=sa.text("'pending'"), nullable=False),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['workspace_uuid'], ['workspaces.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['job_uuid'], ['notification_jobs.uuid'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['target_uuid'], ['notification_targets.uuid'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('uuid'),
            sa.UniqueConstraint(
                'workspace_uuid',
                'job_uuid',
                'position',
                name='uq_notification_attempts_position',
            ),
        )
        op.create_index(
            'ix_notification_attempts_workspace_job',
            'notification_attempts',
            ['workspace_uuid', 'job_uuid'],
            unique=False,
        )

    for table_name in _TABLES:
        if table_name in set(sa.inspect(conn).get_table_names()):
            _install_tenant_policy(conn, table_name)


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = set(sa.inspect(conn).get_table_names())
    for table_name in reversed(_TABLES):
        if table_name not in existing_tables:
            continue
        if conn.dialect.name == 'postgresql':
            table = _quote(conn, table_name)
            policy = _quote(conn, _POLICY_NAME)
            op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON {table}'))
        op.drop_table(table_name)
