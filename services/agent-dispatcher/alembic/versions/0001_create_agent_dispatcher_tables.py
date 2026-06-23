"""Create agent dispatcher tables.

Revision ID: 0001
Revises:
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brainstorm_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", sa.String(255), nullable=False, unique=True),
        sa.Column("project_name", sa.String(255), nullable=False),
        sa.Column("current_round", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_rounds", sa.Integer, nullable=False, server_default="3"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("consensus", sa.String(50), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_brainstorm_sessions_ticket_id", "brainstorm_sessions", ["ticket_id"])
    op.create_index("idx_brainstorm_sessions_status", "brainstorm_sessions", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("runner_mode", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "needs_review",
                "failed",
                "timed_out",
                name="agent_run_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("round_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "brainstorm_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brainstorm_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("context_snapshot", JSONB, nullable=False, server_default="{}"),
        sa.Column("raw_output", sa.Text, nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_agent_runs_ticket_id", "agent_runs", ["ticket_id"])
    op.create_index("idx_agent_runs_status", "agent_runs", ["status"])
    op.create_index("idx_agent_runs_ticket_status", "agent_runs", ["ticket_id", "status"])
    # Enforce at most one running record per ticket at the DB level (prevents TOCTOU double-run)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_agent_runs_ticket_running
        ON agent_runs (ticket_id)
        WHERE status = 'running'
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_new_agent_run()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_notify('df_new_agent_run', row_to_json(NEW)::text);
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_notify_new_agent_run
        AFTER INSERT ON agent_runs
        FOR EACH ROW EXECUTE FUNCTION notify_new_agent_run()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_notify_new_agent_run ON agent_runs")
    op.execute("DROP FUNCTION IF EXISTS notify_new_agent_run")
    op.execute("DROP INDEX IF EXISTS uq_agent_runs_ticket_running")
    op.drop_table("agent_runs")
    op.drop_table("brainstorm_sessions")
    op.execute("DROP TYPE IF EXISTS agent_run_status")
