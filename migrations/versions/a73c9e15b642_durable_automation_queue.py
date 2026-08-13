"""durable automation queue

Revision ID: a73c9e15b642
Revises: f21a58d9c341
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a73c9e15b642"
down_revision: str | None = "f21a58d9c341"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_automation_jobs_job_type", "automation_jobs", ["job_type"], unique=False
    )
    op.create_index(
        "ix_automation_jobs_status", "automation_jobs", ["status"], unique=False
    )
    op.create_index(
        "ix_automation_jobs_dedupe_key", "automation_jobs", ["dedupe_key"], unique=True
    )
    op.create_index(
        "ix_automation_jobs_priority", "automation_jobs", ["priority"], unique=False
    )
    op.create_index(
        "ix_automation_jobs_lease_token", "automation_jobs", ["lease_token"], unique=False
    )
    op.create_index(
        "ix_automation_job_due",
        "automation_jobs",
        ["status", "run_after", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_automation_job_lease",
        "automation_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_automation_job_lease", table_name="automation_jobs")
    op.drop_index("ix_automation_job_due", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_lease_token", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_priority", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_dedupe_key", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_status", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_job_type", table_name="automation_jobs")
    op.drop_table("automation_jobs")
