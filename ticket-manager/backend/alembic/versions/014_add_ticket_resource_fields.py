"""add ticket resource fields

Revision ID: 014
Revises: 013
Create Date: 2026-05-24
"""

import sqlalchemy as sa

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("time_spent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tickets",
        sa.Column("tokens_consumed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("tickets", "tokens_consumed")
    op.drop_column("tickets", "time_spent")
