"""add explicit bot routing mode

Revision ID: 0022_bot_routing_mode
Revises: 0021_merge_reasoning_config
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0022_bot_routing_mode'
down_revision = '0021_merge_reasoning_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'bots' not in inspector.get_table_names():
        return

    columns = {column['name'] for column in inspector.get_columns('bots')}
    if 'routing_mode' in columns:
        return

    # Alembic add_column uses server_default for database-generated defaults.
    # Source: https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.add_column
    op.add_column(
        'bots',
        sa.Column(
            'routing_mode',
            sa.String(32),
            nullable=False,
            server_default=sa.text("'routes_only'"),
        ),
    )

    # Preserve the behavior of every bot that existed before strict routing.
    conn.execute(sa.text("UPDATE bots SET routing_mode = 'fallback_default'"))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'bots' not in inspector.get_table_names():
        return

    columns = {column['name'] for column in inspector.get_columns('bots')}
    if 'routing_mode' not in columns:
        return

    # Batch mode keeps the downgrade compatible with SQLite table rebuilds.
    # Source: https://alembic.sqlalchemy.org/en/latest/batch.html
    with op.batch_alter_table('bots') as batch_op:
        batch_op.drop_column('routing_mode')
