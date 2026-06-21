"""Initial migration: jobs + audit_log."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TYPE job_status AS ENUM ('pending','running','done','failed')")
    op.execute("CREATE TYPE job_type AS ENUM ('orchestrate','distill')")

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.Enum("orchestrate", "distill", name="job_type"), nullable=False),
        sa.Column("ticket_id", sa.String(255), nullable=False, index=True),
        sa.Column("project_id", sa.String(255), nullable=False, index=True),
        sa.Column("status", sa.Enum("pending", "running", "done", "failed", name="job_status"), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("triggered_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ticket_id", sa.String(255), nullable=False, index=True),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("from_state", sa.String(64), nullable=True),
        sa.Column("to_state", sa.String(64), nullable=True),
        sa.Column("assigned_agent", sa.String(64), nullable=True),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("override_logged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("details", sa.Text, nullable=False, server_default=""),
        sa.Column("decision_payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # PostgreSQL NOTIFY trigger on jobs insert
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_new_job() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('df_new_job', NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_notify_new_job
        AFTER INSERT ON jobs
        FOR EACH ROW WHEN (NEW.status = 'pending')
        EXECUTE FUNCTION notify_new_job();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_notify_new_job ON jobs")
    op.execute("DROP FUNCTION IF EXISTS notify_new_job()")
    op.drop_table("audit_log")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS job_type")
