"""Durable progressive Step 1 appraisal jobs.

Revision ID: 82c6d4f1a9b7
Revises: 71e4a2b890c3
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "82c6d4f1a9b7"
down_revision: str | None = "71e4a2b890c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appraisal_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "RUNNING", "DONE", "FAILED", name="appraisaljobstatus"),
            nullable=False,
        ),
        sa.Column("per_source_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("force_refresh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appraisal_jobs_project_id", "appraisal_jobs", ["project_id"])
    op.create_index("ix_appraisal_jobs_domain", "appraisal_jobs", ["domain"])
    op.create_index("ix_appraisal_jobs_status", "appraisal_jobs", ["status"])
    op.create_index("ix_appraisal_jobs_batch_id", "appraisal_jobs", ["batch_id"])
    op.create_index(
        "ix_appraisal_job_status_created", "appraisal_jobs", ["status", "created_at"]
    )
    op.create_index(
        "ix_appraisal_job_batch_status", "appraisal_jobs", ["batch_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_appraisal_job_batch_status", table_name="appraisal_jobs")
    op.drop_index("ix_appraisal_job_status_created", table_name="appraisal_jobs")
    op.drop_index("ix_appraisal_jobs_batch_id", table_name="appraisal_jobs")
    op.drop_index("ix_appraisal_jobs_status", table_name="appraisal_jobs")
    op.drop_index("ix_appraisal_jobs_domain", table_name="appraisal_jobs")
    op.drop_index("ix_appraisal_jobs_project_id", table_name="appraisal_jobs")
    op.drop_table("appraisal_jobs")
