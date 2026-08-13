"""currency normalization and reconciliation ledger

Revision ID: d8a6f4b20317
Revises: c4f76a9b2012
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8a6f4b20317"
down_revision: str | None = "c4f76a9b2012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finance_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("max_rate_age_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO finance_settings "
            "(id, base_currency, max_rate_age_days, created_at, updated_at) "
            "VALUES (1, 'VND', 7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("from_currency", sa.String(length=3), nullable=False),
        sa.Column("to_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(24, 12), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column(
            "review_status",
            sa.Enum(
                "PROPOSED",
                "ACCEPTED",
                "REJECTED",
                name="fxratereviewstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="PROPOSED",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash"),
    )
    op.create_index("ix_fx_rates_rate_date", "fx_rates", ["rate_date"], unique=False)
    op.create_index("ix_fx_rates_from_currency", "fx_rates", ["from_currency"], unique=False)
    op.create_index("ix_fx_rates_to_currency", "fx_rates", ["to_currency"], unique=False)
    op.create_index("ix_fx_rates_source_hash", "fx_rates", ["source_hash"], unique=True)
    op.create_index(
        "ix_fx_rate_pair_date_status",
        "fx_rates",
        ["from_currency", "to_currency", "rate_date", "review_status"],
        unique=False,
    )

    op.create_table(
        "reconciliation_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ATTRIBUTED",
                "PARTIAL",
                "UNATTRIBUTED",
                "DUPLICATE",
                "CONFLICT",
                name="reconciliationstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=120), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_reconciliation_items_status", "reconciliation_items", ["status"], unique=False
    )
    op.create_index(
        "ix_reconciliation_items_entity_type",
        "reconciliation_items",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_items_entity_id",
        "reconciliation_items",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_items_dedupe_key",
        "reconciliation_items",
        ["dedupe_key"],
        unique=True,
    )
    op.create_index(
        "ix_reconciliation_items_resolved_at",
        "reconciliation_items",
        ["resolved_at"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_open_status",
        "reconciliation_items",
        ["resolved_at", "status"],
        unique=False,
    )

    op.add_column("commissions", sa.Column("fx_rate_id", sa.Integer(), nullable=True))
    op.add_column("spend", sa.Column("fx_rate", sa.Numeric(24, 12), nullable=True))
    op.add_column("spend", sa.Column("fx_source", sa.String(length=120), nullable=True))
    op.add_column("spend", sa.Column("fx_rate_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE spend SET normalized_amount = amount, normalized_currency = 'VND', "
            "fx_rate = 1, fx_source = 'IDENTITY' WHERE currency = 'VND'"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO reconciliation_items "
            "(status, entity_type, entity_id, dedupe_key, reason, payload_json, "
            "resolved_at, resolved_by, resolution_note, created_at, updated_at) "
            "SELECT CASE "
            "WHEN cv.click_id IS NOT NULL AND cv.program_id IS NOT NULL THEN 'ATTRIBUTED' "
            "WHEN cv.click_id IS NOT NULL OR cv.program_id IS NOT NULL THEN 'PARTIAL' "
            "ELSE 'UNATTRIBUTED' END, "
            "'COMMISSION', CAST(co.id AS TEXT), 'COMMISSION_ATTRIBUTION:' || co.id, "
            "CASE "
            "WHEN cv.click_id IS NOT NULL AND cv.program_id IS NOT NULL "
            "THEN 'Đã nối commission với click và chương trình.' "
            "WHEN cv.click_id IS NOT NULL THEN 'Đã có click nhưng thiếu chương trình.' "
            "WHEN cv.program_id IS NOT NULL "
            "THEN 'Đã có chương trình nhưng chưa nối được click/SubID.' "
            "ELSE 'Chưa có click/SubID và chưa gắn chương trình.' END, "
            "json_object('external_id', co.external_id, 'has_click', cv.click_id IS NOT NULL, "
            "'has_program', cv.program_id IS NOT NULL, 'currency', co.currency, "
            "'amount', CAST(co.amount AS TEXT)), "
            "CASE WHEN cv.click_id IS NOT NULL AND cv.program_id IS NOT NULL "
            "THEN CURRENT_TIMESTAMP ELSE NULL END, "
            "CASE WHEN cv.click_id IS NOT NULL AND cv.program_id IS NOT NULL "
            "THEN 'system' ELSE NULL END, "
            "CASE WHEN cv.click_id IS NOT NULL AND cv.program_id IS NOT NULL "
            "THEN 'Attribution đầy đủ; không cần xử lý.' ELSE NULL END, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM commissions co LEFT JOIN conversions cv ON cv.id = co.conversion_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE commissions SET normalized_amount = amount, normalized_currency = 'VND', "
            "fx_rate = 1, fx_source = 'IDENTITY' WHERE currency = 'VND'"
        )
    )


def downgrade() -> None:
    op.drop_column("spend", "fx_rate_id")
    op.drop_column("spend", "fx_source")
    op.drop_column("spend", "fx_rate")
    op.drop_column("commissions", "fx_rate_id")

    op.drop_index("ix_reconciliation_open_status", table_name="reconciliation_items")
    op.drop_index("ix_reconciliation_items_resolved_at", table_name="reconciliation_items")
    op.drop_index("ix_reconciliation_items_dedupe_key", table_name="reconciliation_items")
    op.drop_index("ix_reconciliation_items_entity_id", table_name="reconciliation_items")
    op.drop_index("ix_reconciliation_items_entity_type", table_name="reconciliation_items")
    op.drop_index("ix_reconciliation_items_status", table_name="reconciliation_items")
    op.drop_table("reconciliation_items")

    op.drop_index("ix_fx_rate_pair_date_status", table_name="fx_rates")
    op.drop_index("ix_fx_rates_source_hash", table_name="fx_rates")
    op.drop_index("ix_fx_rates_to_currency", table_name="fx_rates")
    op.drop_index("ix_fx_rates_from_currency", table_name="fx_rates")
    op.drop_index("ix_fx_rates_rate_date", table_name="fx_rates")
    op.drop_table("fx_rates")
    op.drop_table("finance_settings")
