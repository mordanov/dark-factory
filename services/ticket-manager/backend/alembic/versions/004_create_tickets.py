"""create tickets table

Revision ID: 004
Revises: 003
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "parent_ticket_id", UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=True
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            ENUM(
                "OPEN",
                "IN_PROGRESS",
                "IN_REVIEW",
                "DONE",
                "CLOSED",
                name="ticket_status",
                create_type=False,
            ),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_tickets_project_id", "tickets", ["project_id"])
    op.create_index("idx_tickets_parent_ticket_id", "tickets", ["parent_ticket_id"])
    op.create_index("idx_tickets_status", "tickets", ["status"])
    op.create_index("idx_tickets_created_by", "tickets", ["created_by"])


def downgrade() -> None:
    op.drop_index("idx_tickets_created_by", table_name="tickets")
    op.drop_index("idx_tickets_status", table_name="tickets")
    op.drop_index("idx_tickets_parent_ticket_id", table_name="tickets")
    op.drop_index("idx_tickets_project_id", table_name="tickets")
    op.drop_table("tickets")
