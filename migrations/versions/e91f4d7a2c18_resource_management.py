"""Resource management, nurture tracking and Camp Plan account binding.

Revision ID: e91f4d7a2c18
Revises: b84d0e26c104
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e91f4d7a2c18"
down_revision: str | None = "b84d0e26c104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(length=320), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="SELF"),
        sa.Column("declared_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("device_changes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status_override", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("device_changes >= 0", name="ck_emails_device_changes_nonnegative"),
        sa.CheckConstraint(
            "status_override IS NULL OR status_override = 'LOCKED'",
            name="ck_emails_status_override",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("address"),
    )
    op.create_index("ix_emails_address", "emails", ["address"], unique=True)

    with op.batch_alter_table("ads_accounts") as batch:
        batch.add_column(sa.Column("email_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("type", sa.String(length=16), nullable=True))
        batch.add_column(
            sa.Column("rent_cost", sa.Numeric(18, 6), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("spend_fee_pct", sa.Numeric(10, 6), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "resource_state", sa.String(length=24), nullable=False, server_default="CHAY"
            )
        )
        batch.add_column(sa.Column("current_project_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("display_name", sa.String(length=255), nullable=True))
        batch.add_column(
            sa.Column("health", sa.String(length=16), nullable=False, server_default="OK")
        )
        batch.add_column(sa.Column("note", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_ads_accounts_email_id", "emails", ["email_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_foreign_key(
            "fk_ads_accounts_current_project_id",
            "projects",
            ["current_project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_ads_accounts_current_project_id", ["current_project_id"]
        )
        batch.create_check_constraint("ck_ads_accounts_rent_cost_nonnegative", "rent_cost >= 0")
        batch.create_check_constraint(
            "ck_ads_accounts_spend_fee_pct_range",
            "spend_fee_pct >= 0 AND spend_fee_pct <= 100",
        )
    op.create_index("ix_ads_accounts_email_id", "ads_accounts", ["email_id"], unique=False)
    op.create_index(
        "ix_ads_accounts_current_project_id",
        "ads_accounts",
        ["current_project_id"],
        unique=True,
    )

    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("monthly_in_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("linked_gateways", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("owner_name", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("monthly_in_usd >= 0", name="ck_resources_monthly_nonnegative"),
        sa.CheckConstraint(
            "type IN ('paypal','payoneer','wise','card','crypto_wallet','exchange',"
            "'sim','device','website','social')",
            name="ck_resources_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resources_type", "resources", ["type"], unique=False)

    op.create_table(
        "nurture_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("tasks_done", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_id", "date", name="uq_nurture_log_email_date"),
    )
    op.create_index("ix_nurture_logs_email_id", "nurture_logs", ["email_id"], unique=False)
    op.create_index("ix_nurture_logs_date", "nurture_logs", ["date"], unique=False)

    op.create_table(
        "ads_account_project_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ads_account_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ads_account_id"], ["ads_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ads_account_id", "project_id", name="uq_ads_account_project_history"
        ),
    )
    op.create_index(
        "ix_ads_account_project_history_ads_account_id",
        "ads_account_project_history",
        ["ads_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_ads_account_project_history_project_id",
        "ads_account_project_history",
        ["project_id"],
        unique=False,
    )

    with op.batch_alter_table("camp_plans") as batch:
        batch.add_column(sa.Column("ads_account_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_camp_plans_ads_account_id",
            "ads_accounts",
            ["ads_account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint("uq_camp_plans_ads_account_id", ["ads_account_id"])
    op.create_index(
        "ix_camp_plans_ads_account_id", "camp_plans", ["ads_account_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_camp_plans_ads_account_id", table_name="camp_plans")
    with op.batch_alter_table("camp_plans") as batch:
        batch.drop_constraint("uq_camp_plans_ads_account_id", type_="unique")
        batch.drop_constraint("fk_camp_plans_ads_account_id", type_="foreignkey")
        batch.drop_column("ads_account_id")

    op.drop_index(
        "ix_ads_account_project_history_project_id",
        table_name="ads_account_project_history",
    )
    op.drop_index(
        "ix_ads_account_project_history_ads_account_id",
        table_name="ads_account_project_history",
    )
    op.drop_table("ads_account_project_history")
    op.drop_index("ix_nurture_logs_date", table_name="nurture_logs")
    op.drop_index("ix_nurture_logs_email_id", table_name="nurture_logs")
    op.drop_table("nurture_logs")
    op.drop_index("ix_resources_type", table_name="resources")
    op.drop_table("resources")

    op.drop_index("ix_ads_accounts_current_project_id", table_name="ads_accounts")
    op.drop_index("ix_ads_accounts_email_id", table_name="ads_accounts")
    with op.batch_alter_table("ads_accounts") as batch:
        batch.drop_constraint("ck_ads_accounts_spend_fee_pct_range", type_="check")
        batch.drop_constraint("ck_ads_accounts_rent_cost_nonnegative", type_="check")
        batch.drop_constraint("uq_ads_accounts_current_project_id", type_="unique")
        batch.drop_constraint("fk_ads_accounts_current_project_id", type_="foreignkey")
        batch.drop_constraint("fk_ads_accounts_email_id", type_="foreignkey")
        batch.drop_column("note")
        batch.drop_column("health")
        batch.drop_column("display_name")
        batch.drop_column("current_project_id")
        batch.drop_column("resource_state")
        batch.drop_column("spend_fee_pct")
        batch.drop_column("rent_cost")
        batch.drop_column("type")
        batch.drop_column("email_id")

    op.drop_index("ix_emails_address", table_name="emails")
    op.drop_table("emails")
