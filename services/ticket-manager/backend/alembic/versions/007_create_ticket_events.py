"""create ticket_events table

Revision ID: 007
Revises: 006
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("ticket_id", UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "actor_role",
            ENUM("administrator", "user", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("prev_state", JSONB, nullable=True),
        sa.Column("new_state", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_ticket_events_ticket_id", "ticket_events", ["ticket_id"])
    op.create_index("idx_ticket_events_occurred_at", "ticket_events", ["occurred_at"])
    op.create_index("idx_ticket_events_event_type", "ticket_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("idx_ticket_events_event_type", table_name="ticket_events")
    op.drop_index("idx_ticket_events_occurred_at", table_name="ticket_events")
    op.drop_index("idx_ticket_events_ticket_id", table_name="ticket_events")
    op.drop_table("ticket_events")
