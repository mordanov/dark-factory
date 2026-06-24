"""add project_groups table and group_id to projects

Revision ID: 017
Revises: 016
Create Date: 2026-06-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_groups",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("identifier", sa.String(8), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("identifier", name="uq_project_groups_identifier"),
    )
    op.create_index("idx_project_groups_identifier", "project_groups", ["identifier"])

    # Seed the DEFAULT system group and capture its UUID for backfill
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "INSERT INTO project_groups (identifier, name, description, is_system) "
            "VALUES ('DEFAULT', 'Default', 'Default group for ungrouped projects', true) "
            "RETURNING id"
        )
    )
    default_id = result.scalar()

    # Add group_id as nullable first so the column can be created on non-empty table
    op.add_column("projects", sa.Column("group_id", PGUUID(as_uuid=True), nullable=True))

    # Backfill all existing projects to the DEFAULT group
    conn.execute(sa.text("UPDATE projects SET group_id = :gid").bindparams(gid=default_id))

    # Now enforce NOT NULL
    op.alter_column("projects", "group_id", nullable=False)

    op.create_foreign_key(
        "fk_projects_group_id",
        "projects",
        "project_groups",
        ["group_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("idx_projects_group_id", "projects", ["group_id"])


def downgrade() -> None:
    op.drop_index("idx_projects_group_id", table_name="projects")
    op.drop_constraint("fk_projects_group_id", "projects", type_="foreignkey")
    op.drop_column("projects", "group_id")
    op.drop_index("idx_project_groups_identifier", table_name="project_groups")
    op.drop_table("project_groups")
