"""Camp Doctor diagnosis and read-only change history.

Revision ID: 6b1d8e2c4108
Revises: 4f7c2a91d5e0
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b1d8e2c4108"
down_revision: str | None = "4f7c2a91d5e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camp_diagnoses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_camp_diagnoses_campaign_id", "camp_diagnoses", ["campaign_id"])
    op.create_index("ix_camp_diagnoses_run_at", "camp_diagnoses", ["run_at"])

    op.create_table(
        "change_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_change_events_campaign_id", "change_events", ["campaign_id"])
    op.create_index("ix_change_events_external_id", "change_events", ["external_id"], unique=True)
    op.create_index("ix_change_events_field_name", "change_events", ["field_name"])
    op.create_index("ix_change_events_changed_at", "change_events", ["changed_at"])


def downgrade() -> None:
    op.drop_index("ix_change_events_changed_at", table_name="change_events")
    op.drop_index("ix_change_events_field_name", table_name="change_events")
    op.drop_index("ix_change_events_external_id", table_name="change_events")
    op.drop_index("ix_change_events_campaign_id", table_name="change_events")
    op.drop_table("change_events")
    op.drop_index("ix_camp_diagnoses_run_at", table_name="camp_diagnoses")
    op.drop_index("ix_camp_diagnoses_campaign_id", table_name="camp_diagnoses")
    op.drop_table("camp_diagnoses")
