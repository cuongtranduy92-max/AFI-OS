"""Project portfolio, workflow and versioned metric provenance.

Revision ID: f21a58d9c341
Revises: d8a6f4b20317
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f21a58d9c341"
down_revision: str | None = "d8a6f4b20317"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROJECT_STAGES = (
    "INTAKE",
    "RESEARCH",
    "EVALUATION",
    "PREP",
    "LIVE",
    "PAUSED",
    "CLOSED",
)
REGISTRATION_STATUSES = (
    "NOT_STARTED",
    "APPLYING",
    "PENDING_APPROVAL",
    "APPROVED",
    "BLOCKED_REGISTRATION",
    "REJECTED",
    "CLOSED",
)
DATA_QUALITIES = (
    "OBSERVED",
    "IMPORTED",
    "MATCHED",
    "ESTIMATED",
    "MODELED",
    "UNKNOWN",
)


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column(
                "stage",
                sa.Enum(*PROJECT_STAGES, name="projectstage", native_enum=False),
                nullable=False,
                server_default="INTAKE",
            )
        )
        batch.add_column(
            sa.Column(
                "registration_status",
                sa.Enum(
                    *REGISTRATION_STATUSES,
                    name="registrationstatus",
                    native_enum=False,
                ),
                nullable=False,
                server_default="NOT_STARTED",
            )
        )
        batch.add_column(sa.Column("owner", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("next_action", sa.String(length=500), nullable=True))
        batch.add_column(
            sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(length=120), nullable=False),
        sa.Column("numeric_value", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column(
            "quality",
            sa.Enum(*DATA_QUALITIES, name="dataquality", native_enum=False),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("geography", sa.String(length=120), nullable=True),
        sa.Column("language", sa.String(length=40), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("method_version", sa.String(length=80), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash"),
    )
    op.create_index(
        op.f("ix_metric_snapshots_metric_key"),
        "metric_snapshots",
        ["metric_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metric_snapshots_project_id"),
        "metric_snapshots",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metric_snapshots_source_hash"),
        "metric_snapshots",
        ["source_hash"],
        unique=True,
    )
    op.create_index(
        "ix_metric_snapshot_project_key_observed",
        "metric_snapshots",
        ["project_id", "metric_key", "observed_at"],
        unique=False,
    )

    # Link any existing observation-created project to the oldest Program on the same domain.
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET program_id = (
                    SELECT p.id
                    FROM programs AS p
                    JOIN merchants AS m ON m.id = p.merchant_id
                    WHERE m.website_domain = projects.domain
                    ORDER BY p.id
                    LIMIT 1
                ),
                affiliate_program_found = 1
            WHERE program_id IS NULL
              AND EXISTS (
                    SELECT 1
                    FROM programs AS p
                    JOIN merchants AS m ON m.id = p.merchant_id
                    WHERE m.website_domain = projects.domain
                )
            """
        )
    )

    # Programs already present in 0.2.x become retained Projects without changing Program truth.
    op.execute(
        sa.text(
            """
            INSERT INTO projects (
                domain, brand_name, category, affiliate_program_found, program_id,
                watch_status, stage, registration_status, owner, next_action,
                next_action_due_at, first_seen_at, last_seen_at, notes,
                created_at, updated_at
            )
            SELECT
                m.website_domain,
                m.name,
                NULL,
                1,
                p.id,
                'WATCH',
                CASE p.status
                    WHEN 'ACTIVE' THEN 'LIVE'
                    WHEN 'PAUSED' THEN 'PAUSED'
                    WHEN 'REJECTED' THEN 'CLOSED'
                    WHEN 'CLOSED' THEN 'CLOSED'
                    WHEN 'APPLYING' THEN 'PREP'
                    WHEN 'PENDING_APPROVAL' THEN 'PREP'
                    ELSE 'RESEARCH'
                END,
                CASE p.status
                    WHEN 'ACTIVE' THEN 'APPROVED'
                    WHEN 'PAUSED' THEN 'BLOCKED_REGISTRATION'
                    WHEN 'REJECTED' THEN 'REJECTED'
                    WHEN 'CLOSED' THEN 'CLOSED'
                    WHEN 'APPLYING' THEN 'APPLYING'
                    WHEN 'PENDING_APPROVAL' THEN 'PENDING_APPROVAL'
                    ELSE 'NOT_STARTED'
                END,
                NULL,
                CASE p.status
                    WHEN 'ACTIVE' THEN 'Theo dõi campaign và doanh thu'
                    WHEN 'PAUSED' THEN 'Kiểm tra lại khả năng đăng ký hoặc giữ PAUSED'
                    WHEN 'PENDING_APPROVAL' THEN 'Theo dõi phản hồi đăng ký'
                    WHEN 'APPLYING' THEN 'Hoàn tất hồ sơ đăng ký'
                    ELSE 'Hoàn tất research và hồ sơ đăng ký'
                END,
                NULL,
                p.created_at,
                p.updated_at,
                NULL,
                p.created_at,
                p.updated_at
            FROM programs AS p
            JOIN merchants AS m ON m.id = p.merchant_id
            WHERE p.id = (
                    SELECT MIN(p2.id)
                    FROM programs AS p2
                    WHERE p2.merchant_id = p.merchant_id
                )
              AND NOT EXISTS (
                    SELECT 1 FROM projects AS existing
                    WHERE existing.domain = m.website_domain
                )
            """
        )
    )

    # Normalize workflow fields for projects linked before the insert above.
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET stage = CASE (
                    SELECT status FROM programs WHERE programs.id = projects.program_id
                )
                    WHEN 'ACTIVE' THEN 'LIVE'
                    WHEN 'PAUSED' THEN 'PAUSED'
                    WHEN 'REJECTED' THEN 'CLOSED'
                    WHEN 'CLOSED' THEN 'CLOSED'
                    WHEN 'APPLYING' THEN 'PREP'
                    WHEN 'PENDING_APPROVAL' THEN 'PREP'
                    ELSE stage
                END,
                registration_status = CASE (
                    SELECT status FROM programs WHERE programs.id = projects.program_id
                )
                    WHEN 'ACTIVE' THEN 'APPROVED'
                    WHEN 'PAUSED' THEN 'BLOCKED_REGISTRATION'
                    WHEN 'REJECTED' THEN 'REJECTED'
                    WHEN 'CLOSED' THEN 'CLOSED'
                    WHEN 'APPLYING' THEN 'APPLYING'
                    WHEN 'PENDING_APPROVAL' THEN 'PENDING_APPROVAL'
                    ELSE registration_status
                END
            WHERE program_id IS NOT NULL
            """
        )
    )

    # A campaign mapped to a Program inherits only the local Project link; no Ads write occurs.
    op.execute(
        sa.text(
            """
            UPDATE campaigns
            SET project_id = (
                SELECT projects.id
                FROM campaign_program_links
                JOIN projects ON projects.program_id = campaign_program_links.program_id
                WHERE campaign_program_links.campaign_id = campaigns.id
                LIMIT 1
            )
            WHERE project_id IS NULL
              AND EXISTS (
                SELECT 1
                FROM campaign_program_links
                JOIN projects ON projects.program_id = campaign_program_links.program_id
                WHERE campaign_program_links.campaign_id = campaigns.id
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_metric_snapshot_project_key_observed",
        table_name="metric_snapshots",
    )
    op.drop_index(
        op.f("ix_metric_snapshots_source_hash"),
        table_name="metric_snapshots",
    )
    op.drop_index(
        op.f("ix_metric_snapshots_project_id"),
        table_name="metric_snapshots",
    )
    op.drop_index(
        op.f("ix_metric_snapshots_metric_key"),
        table_name="metric_snapshots",
    )
    op.drop_table("metric_snapshots")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("next_action_due_at")
        batch.drop_column("next_action")
        batch.drop_column("owner")
        batch.drop_column("registration_status")
        batch.drop_column("stage")
