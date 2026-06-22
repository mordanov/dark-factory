"""add tags

Revision ID: 012
Revises: 011
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tags_name"),
    )
    op.create_index("idx_tags_name", "tags", ["name"])

    op.create_table(
        "ticket_tags",
        sa.Column("ticket_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", PG_UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticket_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("ticket_tags")
    op.drop_index("idx_tags_name", table_name="tags")
    op.drop_table("tags")
