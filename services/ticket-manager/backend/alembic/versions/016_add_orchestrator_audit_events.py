"""add orchestrator_audit_events table

Revision ID: 016
Revises: 015
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestrator_audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("from_state", sa.String(50), nullable=True),
        sa.Column("to_state", sa.String(50), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "idx_orchestrator_audit_ticket_id",
        "orchestrator_audit_events",
        ["ticket_id"],
    )
    op.create_index(
        "idx_orchestrator_audit_timestamp",
        "orchestrator_audit_events",
        ["timestamp"],
    )


def downgrade() -> None:
    op.drop_index("idx_orchestrator_audit_timestamp", table_name="orchestrator_audit_events")
    op.drop_index("idx_orchestrator_audit_ticket_id", table_name="orchestrator_audit_events")
    op.drop_table("orchestrator_audit_events")
