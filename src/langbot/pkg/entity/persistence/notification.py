from __future__ import annotations

import sqlalchemy

from .base import Base


TARGET_TYPES = frozenset({'person', 'group'})

JOB_STATUS_PENDING = 'pending'
JOB_STATUS_SUCCEEDED = 'succeeded'
JOB_STATUS_PARTIAL_FAILED = 'partial_failed'
JOB_STATUS_FAILED = 'failed'

ATTEMPT_STATUS_PENDING = 'pending'
ATTEMPT_STATUS_SENT = 'sent'
ATTEMPT_STATUS_FAILED = 'failed'


class NotificationTarget(Base):
    """A reusable messaging-platform destination owned by one Workspace."""

    __tablename__ = 'notification_targets'

    uuid = sqlalchemy.Column(sqlalchemy.String(36), primary_key=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    target_type = sqlalchemy.Column(sqlalchemy.String(16), nullable=False)
    target_id = sqlalchemy.Column(sqlalchemy.String(512), nullable=False)
    enabled = sqlalchemy.Column(
        sqlalchemy.Boolean,
        nullable=False,
        default=True,
        server_default=sqlalchemy.true(),
    )
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )

    __table_args__ = (
        sqlalchemy.ForeignKeyConstraint(
            ['workspace_uuid', 'bot_uuid'],
            ['bots.workspace_uuid', 'bots.uuid'],
            name='fk_notification_targets_workspace_bot',
            ondelete='CASCADE',
        ),
        sqlalchemy.CheckConstraint(
            "target_type IN ('person', 'group')",
            name='ck_notification_targets_type',
        ),
        sqlalchemy.UniqueConstraint(
            'workspace_uuid',
            'bot_uuid',
            'target_type',
            'target_id',
            name='uq_notification_targets_destination',
        ),
        sqlalchemy.Index('ix_notification_targets_workspace_name', 'workspace_uuid', 'name'),
    )


class NotificationJob(Base):
    """One idempotent multi-target notification request."""

    __tablename__ = 'notification_jobs'

    uuid = sqlalchemy.Column(sqlalchemy.String(36), primary_key=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    idempotency_key = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    request_hash = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    message_chain = sqlalchemy.Column(sqlalchemy.JSON, nullable=False)
    status = sqlalchemy.Column(
        sqlalchemy.String(32),
        nullable=False,
        default=JOB_STATUS_PENDING,
        server_default=sqlalchemy.text("'pending'"),
    )
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
            'idempotency_key',
            name='uq_notification_jobs_idempotency',
        ),
        sqlalchemy.Index('ix_notification_jobs_workspace_created', 'workspace_uuid', 'created_at'),
    )


class NotificationAttempt(Base):
    """The durable result for one destination within a notification job."""

    __tablename__ = 'notification_attempts'

    uuid = sqlalchemy.Column(sqlalchemy.String(36), primary_key=True)
    workspace_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('workspaces.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    job_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('notification_jobs.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    target_uuid = sqlalchemy.Column(
        sqlalchemy.String(36),
        sqlalchemy.ForeignKey('notification_targets.uuid', ondelete='SET NULL'),
        nullable=True,
    )
    position = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    target_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    target_type = sqlalchemy.Column(sqlalchemy.String(16), nullable=False)
    target_id = sqlalchemy.Column(sqlalchemy.String(512), nullable=False)
    status = sqlalchemy.Column(
        sqlalchemy.String(32),
        nullable=False,
        default=ATTEMPT_STATUS_PENDING,
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
            'job_uuid',
            'position',
            name='uq_notification_attempts_position',
        ),
        sqlalchemy.Index('ix_notification_attempts_workspace_job', 'workspace_uuid', 'job_uuid'),
    )
