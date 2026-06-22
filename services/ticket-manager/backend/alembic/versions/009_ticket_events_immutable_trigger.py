"""ticket_events immutable trigger (F-EVT-01 security fix)

Revision ID: 009
Revises: 008
Create Date: 2026-05-23

Adds a PostgreSQL trigger that raises an exception on any UPDATE or DELETE
against ticket_events, enforcing the append-only invariant at the DB layer.
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_ticket_events_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'ticket_events is append-only — UPDATE/DELETE not permitted';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER ticket_events_immutable
        BEFORE UPDATE OR DELETE ON ticket_events
        FOR EACH ROW EXECUTE FUNCTION prevent_ticket_events_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ticket_events_immutable ON ticket_events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_ticket_events_mutation();")
