"""Add advertiser discovery state and API usage ledger.

Revision ID: 93d7e5a2b1c4
Revises: 82c6d4f1a9b7
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "93d7e5a2b1c4"
down_revision: str | None = "82c6d4f1a9b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column(
            "stage",
            existing_type=sa.String(length=10),
            type_=sa.String(length=12),
            existing_nullable=False,
            existing_server_default="INTAKE",
        )
    with op.batch_alter_table("advertisers") as batch_op:
        batch_op.add_column(
            sa.Column("domain_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("is_goldmine", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_watchlisted", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("last_expanded_at", sa.DateTime(timezone=True)))
    op.create_table(
        "advertiser_api_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_advertiser_api_usage_usage_date",
        "advertiser_api_usage",
        ["usage_date"],
    )
    op.create_index(
        "ix_advertiser_api_usage_endpoint",
        "advertiser_api_usage",
        ["endpoint"],
    )
    op.create_index(
        "ix_advertiser_usage_date_endpoint",
        "advertiser_api_usage",
        ["usage_date", "endpoint"],
    )


def downgrade() -> None:
    op.drop_index("ix_advertiser_usage_date_endpoint", table_name="advertiser_api_usage")
    op.drop_index("ix_advertiser_api_usage_endpoint", table_name="advertiser_api_usage")
    op.drop_index("ix_advertiser_api_usage_usage_date", table_name="advertiser_api_usage")
    op.drop_table("advertiser_api_usage")
    with op.batch_alter_table("advertisers") as batch_op:
        batch_op.drop_column("last_expanded_at")
        batch_op.drop_column("is_watchlisted")
        batch_op.drop_column("is_goldmine")
        batch_op.drop_column("domain_count")
    op.execute("UPDATE projects SET stage = 'INTAKE' WHERE stage = 'DISCOVERED'")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column(
            "stage",
            existing_type=sa.String(length=12),
            type_=sa.String(length=10),
            existing_nullable=False,
            existing_server_default="INTAKE",
        )
