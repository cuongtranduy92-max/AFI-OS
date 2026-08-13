"""campaign risk and exposure

Revision ID: c4f76a9b2012
Revises: 91c2e41e7a01
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f76a9b2012"
down_revision: str | None = "91c2e41e7a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_program_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("link_source", sa.String(length=80), nullable=False, server_default="MANUAL"),
        sa.Column("risk_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_acknowledged_by", sa.String(length=120), nullable=True),
        sa.Column("risk_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_campaign_program_link_campaign"),
    )
    op.create_index(
        "ix_campaign_program_links_campaign_id",
        "campaign_program_links",
        ["campaign_id"],
        unique=True,
    )
    op.create_index(
        "ix_campaign_program_links_program_id",
        "campaign_program_links",
        ["program_id"],
        unique=False,
    )

    op.create_table(
        "campaign_daily_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="GOOGLE_ADS_CSV"),
        sa.Column("quality", sa.String(length=20), nullable=False, server_default="OBSERVED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "metric_date",
            "source",
            name="uq_campaign_daily_stats_source",
        ),
    )
    op.create_index(
        "ix_campaign_daily_stats_campaign_id",
        "campaign_daily_stats",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_daily_stats_metric_date",
        "campaign_daily_stats",
        ["metric_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_daily_stats_metric_date", table_name="campaign_daily_stats")
    op.drop_index("ix_campaign_daily_stats_campaign_id", table_name="campaign_daily_stats")
    op.drop_table("campaign_daily_stats")
    op.drop_index("ix_campaign_program_links_program_id", table_name="campaign_program_links")
    op.drop_index("ix_campaign_program_links_campaign_id", table_name="campaign_program_links")
    op.drop_table("campaign_program_links")
