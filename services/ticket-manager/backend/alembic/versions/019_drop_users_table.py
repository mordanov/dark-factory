"""DESTRUCTIVE: drops all user data

Revision ID: 019
Revises: 018
Create Date: 2026-06-24
"""

import sqlalchemy as sa

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Drop refresh_tokens table (FK to users.id)
    op.drop_table("refresh_tokens")

    # --- tickets.created_by ---
    # Step 2a: Add TEXT column, copy UUID data, drop FK+old column, rename
    op.add_column("tickets", sa.Column("created_by_text", sa.Text(), nullable=True))
    op.execute("UPDATE tickets SET created_by_text = created_by::text")
    op.alter_column("tickets", "created_by_text", nullable=False)
    op.drop_constraint("tickets_created_by_fkey", "tickets", type_="foreignkey")
    op.drop_index("idx_tickets_created_by", table_name="tickets")
    op.drop_column("tickets", "created_by")
    op.alter_column("tickets", "created_by_text", new_column_name="created_by")
    op.create_index("idx_tickets_created_by", "tickets", ["created_by"])

    # --- projects.created_by ---
    op.add_column("projects", sa.Column("created_by_text", sa.Text(), nullable=True))
    op.execute("UPDATE projects SET created_by_text = created_by::text")
    op.alter_column("projects", "created_by_text", nullable=False)
    op.drop_constraint("projects_created_by_fkey", "projects", type_="foreignkey")
    op.drop_column("projects", "created_by")
    op.alter_column("projects", "created_by_text", new_column_name="created_by")

    # --- ticket_assignments.user_id ---
    op.add_column("ticket_assignments", sa.Column("user_id_text", sa.Text(), nullable=True))
    op.execute("UPDATE ticket_assignments SET user_id_text = user_id::text")
    op.alter_column("ticket_assignments", "user_id_text", nullable=False)
    op.drop_constraint("ticket_assignments_user_id_fkey", "ticket_assignments", type_="foreignkey")
    op.drop_index("idx_ticket_assignments_user_id", table_name="ticket_assignments")
    op.drop_column("ticket_assignments", "user_id")
    op.alter_column("ticket_assignments", "user_id_text", new_column_name="user_id")
    op.create_index("idx_ticket_assignments_user_id", "ticket_assignments", ["user_id"])

    # --- ticket_assignments.assigned_by ---
    op.add_column("ticket_assignments", sa.Column("assigned_by_text", sa.Text(), nullable=True))
    op.execute("UPDATE ticket_assignments SET assigned_by_text = assigned_by::text")
    op.alter_column("ticket_assignments", "assigned_by_text", nullable=False)
    op.drop_constraint(
        "ticket_assignments_assigned_by_fkey", "ticket_assignments", type_="foreignkey"
    )
    op.drop_column("ticket_assignments", "assigned_by")
    op.alter_column("ticket_assignments", "assigned_by_text", new_column_name="assigned_by")

    # --- ticket_events.actor_id ---
    op.add_column("ticket_events", sa.Column("actor_id_text", sa.Text(), nullable=True))
    op.execute("UPDATE ticket_events SET actor_id_text = actor_id::text")
    op.alter_column("ticket_events", "actor_id_text", nullable=False)
    op.drop_constraint("ticket_events_actor_id_fkey", "ticket_events", type_="foreignkey")
    op.drop_column("ticket_events", "actor_id")
    op.alter_column("ticket_events", "actor_id_text", new_column_name="actor_id")

    # --- progress_updates.user_id ---
    op.add_column("progress_updates", sa.Column("user_id_text", sa.Text(), nullable=True))
    op.execute("UPDATE progress_updates SET user_id_text = user_id::text")
    op.alter_column("progress_updates", "user_id_text", nullable=False)
    op.drop_constraint("progress_updates_user_id_fkey", "progress_updates", type_="foreignkey")
    op.drop_column("progress_updates", "user_id")
    op.alter_column("progress_updates", "user_id_text", new_column_name="user_id")

    # Step N: Drop users table (all FKs removed above)
    op.drop_table("users")


def downgrade() -> None:
    raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal (constitution §XXI)")
