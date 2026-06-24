"""add tokens_spent column to tickets

Revision ID: 018
Revises: 017
Create Date: 2026-06-24
"""

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("tokens_spent", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_tickets_tokens_spent_non_negative",
        "tickets",
        "tokens_spent >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tickets_tokens_spent_non_negative", "tickets", type_="check")
    op.drop_column("tickets", "tokens_spent")
