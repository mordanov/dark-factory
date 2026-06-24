"""Add planning agent: extend session_status, add plan_status enum, create prompt_plans table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_add_planning_agent"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'planning'"))
    op.execute(sa.text("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'plan_ready'"))
    op.execute(sa.text("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'plan_confirmed'"))
    op.execute(sa.text("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'tickets_created'"))
    op.execute(
        sa.text("""
        DO $$
        BEGIN
            CREATE TYPE plan_status AS ENUM (
                'draft', 'ready', 'confirmed', 'tickets_created', 'error'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
    """)
    )

    op.create_table(
        "prompt_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "ready",
                "confirmed",
                "tickets_created",
                "error",
                name="plan_status",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("plan_content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_ticket_ids", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("ticket_id_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tm_epic_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["prompt_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_prompt_plans_session_id"),
    )

    op.create_index("ix_prompt_plans_status", "prompt_plans", ["status"])


def downgrade() -> None:
    op.drop_index("ix_prompt_plans_status", table_name="prompt_plans")
    op.drop_table("prompt_plans")
    op.execute("DROP TYPE IF EXISTS plan_status")
