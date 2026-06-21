"""add project code

Revision ID: 010
Revises: 009
Create Date: 2026-05-23
"""

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("code", sa.String(8), nullable=True))
    op.create_unique_constraint("uq_projects_code", "projects", ["code"])
    op.create_index("idx_projects_code", "projects", ["code"])


def downgrade() -> None:
    op.drop_index("idx_projects_code", table_name="projects")
    op.drop_constraint("uq_projects_code", "projects", type_="unique")
    op.drop_column("projects", "code")
