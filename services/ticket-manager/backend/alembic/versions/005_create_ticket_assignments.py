"""create ticket_assignments table

Revision ID: 005
Revises: 004
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_assignments",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("ticket_id", UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_ticket_assignments_ticket_user", "ticket_assignments", ["ticket_id", "user_id"]
    )
    op.create_index("idx_ticket_assignments_ticket_id", "ticket_assignments", ["ticket_id"])
    op.create_index("idx_ticket_assignments_user_id", "ticket_assignments", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_ticket_assignments_user_id", table_name="ticket_assignments")
    op.drop_index("idx_ticket_assignments_ticket_id", table_name="ticket_assignments")
    op.drop_table("ticket_assignments")
