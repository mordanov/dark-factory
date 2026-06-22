"""add fsm fields to tickets

Revision ID: 015
Revises: 014
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

fsm_status_enum = postgresql.ENUM(
    "backlog",
    "triage",
    "specification",
    "architecture_review",
    "implementation",
    "code_review",
    "security_review",
    "testing",
    "release",
    "done",
    "BLOCKED",
    name="fsm_status_enum",
)


def upgrade() -> None:
    fsm_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "tickets", sa.Column("fsm_status", sa.Enum(name="fsm_status_enum"), nullable=True)
    )
    op.add_column("tickets", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("brainstorm_round", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tickets", sa.Column("assigned_agent", sa.String(255), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("override", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("tickets", sa.Column("override_reason", sa.Text(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("last_orchestrator_run", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "orchestrator_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_index("idx_tickets_fsm_status", "tickets", ["fsm_status"])
    op.create_index(
        "idx_tickets_pending",
        "tickets",
        ["updated_at", "id"],
        postgresql_where=sa.text("fsm_status IS DISTINCT FROM 'done'"),
    )


def downgrade() -> None:
    op.drop_index("idx_tickets_pending", table_name="tickets")
    op.drop_index("idx_tickets_fsm_status", table_name="tickets")

    op.drop_column("tickets", "orchestrator_errors")
    op.drop_column("tickets", "last_orchestrator_run")
    op.drop_column("tickets", "override_reason")
    op.drop_column("tickets", "override")
    op.drop_column("tickets", "assigned_agent")
    op.drop_column("tickets", "brainstorm_round")
    op.drop_column("tickets", "blocked_reason")
    op.drop_column("tickets", "fsm_status")

    fsm_status_enum.drop(op.get_bind(), checkfirst=True)
