"""Add agent maturity tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_worker_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", sa.String(64), nullable=False),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "idle",
                "busy",
                "draining",
                "offline",
                "unhealthy",
                name="worker_status",
            ),
            nullable=False,
            server_default="idle",
        ),
        sa.Column("capabilities_snapshot", JSONB, nullable=False, server_default="{}"),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("offline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_worker_records_role_status",
        "agent_worker_records",
        ["role_id", "status"],
    )
    op.create_index(
        "idx_worker_records_heartbeat",
        "agent_worker_records",
        ["last_heartbeat_at"],
    )
    op.create_index("idx_worker_records_run_id", "agent_worker_records", ["run_id"])

    op.create_table(
        "agent_lifecycle_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "worker_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_worker_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_lifecycle_events_worker_time",
        "agent_lifecycle_events",
        ["worker_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "idx_lifecycle_events_role_time",
        "agent_lifecycle_events",
        ["role_id", sa.text("occurred_at DESC")],
    )

    op.create_table(
        "working_memory_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", sa.String(64), nullable=False),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_role_id", sa.String(64), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column(
            "content",
            sa.Text,
            nullable=False,
            # 65536 char limit enforced at application layer
        ),
        sa.Column(
            "tags",
            ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '30 days'"),
        ),
        sa.CheckConstraint(
            "entry_type IN ('observation','decision','artifact_ref','question','answer')",
            name="ck_wm_entry_type",
        ),
    )
    op.create_index(
        "idx_wm_entries_ticket_time",
        "working_memory_entries",
        ["ticket_id", sa.text("created_at ASC")],
    )
    op.create_index(
        "idx_wm_entries_ticket_author",
        "working_memory_entries",
        ["ticket_id", "author_role_id"],
    )
    op.create_index("idx_wm_entries_expires", "working_memory_entries", ["expires_at"])


def downgrade() -> None:
    op.drop_table("working_memory_entries")
    op.drop_table("agent_lifecycle_events")
    op.drop_table("agent_worker_records")
    op.execute("DROP TYPE IF EXISTS worker_status")
