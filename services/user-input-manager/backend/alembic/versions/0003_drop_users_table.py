"""DESTRUCTIVE: drops all user data

Revision ID: 0003_drop_users_table
Revises: 0002_add_planning_agent
Create Date: 2026-06-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_drop_users_table"
down_revision = "0002_add_planning_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add TEXT column to hold the Keycloak sub value
    op.add_column("prompt_sessions", sa.Column("user_id_text", sa.Text(), nullable=True))

    # Step 2: Populate TEXT column from existing UUID values
    op.execute("UPDATE prompt_sessions SET user_id_text = user_id::text")

    # Step 3: Make TEXT column NOT NULL now that it's populated
    op.alter_column("prompt_sessions", "user_id_text", nullable=False)

    # Step 4: Drop FK constraint and original UUID column
    op.drop_constraint("prompt_sessions_user_id_fkey", "prompt_sessions", type_="foreignkey")
    op.drop_column("prompt_sessions", "user_id")

    # Step 5: Rename TEXT column to user_id
    op.alter_column("prompt_sessions", "user_id_text", new_column_name="user_id")

    # Step 6: Drop the users table (irreversible)
    op.drop_table("users")


def downgrade() -> None:
    raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal (constitution §XXI)")
