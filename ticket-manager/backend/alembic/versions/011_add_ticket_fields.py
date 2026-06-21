"""add ticket fields: number, type, spec, flags

Revision ID: 011
Revises: 010
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE ticket_type AS ENUM "
        "('bug','feature','improvement','investigation','discovery','reporting','testing','analysis','other')"
    )
    op.execute(
        "CREATE TYPE ticket_spec AS ENUM "
        "('backend','frontend','architecture','testing','business_analysis','product_management','other')"
    )

    op.add_column("tickets", sa.Column("number", sa.Integer(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column(
            "ticket_type",
            ENUM(
                "bug",
                "feature",
                "improvement",
                "investigation",
                "discovery",
                "reporting",
                "testing",
                "analysis",
                "other",
                name="ticket_type",
                create_type=False,
            ),
            nullable=False,
            server_default="feature",
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "ticket_spec",
            ENUM(
                "backend",
                "frontend",
                "architecture",
                "testing",
                "business_analysis",
                "product_management",
                "other",
                name="ticket_spec",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "tickets", sa.Column("urgent", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column(
        "tickets", sa.Column("blocker", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column(
        "tickets", sa.Column("bugfix", sa.Boolean(), nullable=False, server_default="false")
    )
    op.create_index("idx_tickets_project_number", "tickets", ["project_id", "number"])


def downgrade() -> None:
    op.drop_index("idx_tickets_project_number", table_name="tickets")
    op.drop_column("tickets", "bugfix")
    op.drop_column("tickets", "blocker")
    op.drop_column("tickets", "urgent")
    op.drop_column("tickets", "ticket_spec")
    op.drop_column("tickets", "ticket_type")
    op.drop_column("tickets", "number")
    op.execute("DROP TYPE ticket_spec")
    op.execute("DROP TYPE ticket_type")
