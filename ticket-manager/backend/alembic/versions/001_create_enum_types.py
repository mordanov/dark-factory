"""create enum types

Revision ID: 001
Revises:
Create Date: 2026-05-23
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE user_role AS ENUM ('administrator', 'user')")
    op.execute(
        "CREATE TYPE ticket_status AS ENUM ('OPEN', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', 'CLOSED')"
    )


def downgrade() -> None:
    op.execute("DROP TYPE IF EXISTS ticket_status")
    op.execute("DROP TYPE IF EXISTS user_role")
