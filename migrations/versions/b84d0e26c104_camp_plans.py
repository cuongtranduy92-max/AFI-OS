"""Step 2 campaign content plans and linter state.

Revision ID: b84d0e26c104
Revises: a73c9e15b642
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b84d0e26c104"
down_revision: str | None = "a73c9e15b642"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camp_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("ref_url", sa.String(length=1000), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("linter_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_camp_plans_project_id"),
    )
    op.create_index("ix_camp_plans_project_id", "camp_plans", ["project_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_camp_plans_project_id", table_name="camp_plans")
    op.drop_table("camp_plans")
