"""Initial migration: create all tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.execute("""
        DO $$
        BEGIN
            CREATE TYPE session_status AS ENUM ('in_progress', 'approved', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            CREATE TYPE session_type AS ENUM ('new_project', 'existing_project');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
    """)

    op.create_table(
        "prompt_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_type", postgresql.ENUM("new_project", "existing_project", name="session_type", create_type=False), nullable=False),
        sa.Column("tm_project_id", sa.String(255), nullable=True),
        sa.Column("tm_project_name", sa.String(255), nullable=True),
        sa.Column("tm_ticket_id", sa.String(255), nullable=True),
        sa.Column("tm_ticket_title", sa.String(500), nullable=True),
        sa.Column("status", postgresql.ENUM("in_progress", "approved", "cancelled", name="session_status", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute("""
        DO $$
        BEGIN
            CREATE TYPE iteration_role AS ENUM ('user', 'assistant');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
    """)

    op.create_table(
        "prompt_iterations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("role", postgresql.ENUM("user", "assistant", name="iteration_role", create_type=False), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("llm_assessment", sa.Text(), nullable=True),
        sa.Column("llm_questions", sa.Text(), nullable=True),
        sa.Column("llm_suggested_title", sa.String(500), nullable=True),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["prompt_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_prompt_sessions_user_id", "prompt_sessions", ["user_id"])
    op.create_index("ix_prompt_iterations_session_id", "prompt_iterations", ["session_id"])


def downgrade() -> None:
    op.drop_table("prompt_iterations")
    op.drop_table("prompt_sessions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS iteration_role")
    op.execute("DROP TYPE IF EXISTS session_status")
    op.execute("DROP TYPE IF EXISTS session_type")
