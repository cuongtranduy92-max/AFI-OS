"""terms evidence proposals and commission fact conflicts

Revision ID: 91c2e41e7a01
Revises: 316f91001198
Create Date: 2026-08-10 20:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "91c2e41e7a01"
down_revision: Union[str, None] = "316f91001198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "terms_evidence",
        sa.Column(
            "scope", sa.String(length=80), nullable=False, server_default="PAID_SEARCH"
        ),
    )
    op.add_column(
        "terms_evidence",
        sa.Column(
            "review_status",
            sa.Enum(
                "PROPOSED",
                "ACCEPTED",
                "REJECTED",
                name="evidencereviewstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="PROPOSED",
        ),
    )
    op.add_column(
        "terms_evidence",
        sa.Column(
            "source_authority",
            sa.Enum(
                "OFFICIAL",
                "PARTNER_PORTAL",
                "WRITTEN_CONFIRMATION",
                "THIRD_PARTY",
                "UNKNOWN",
                name="sourceauthority",
                native_enum=False,
            ),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "terms_evidence",
        sa.Column(
            "collected_by", sa.String(length=80), nullable=False, server_default="MANUAL"
        ),
    )
    op.add_column(
        "terms_evidence", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "terms_evidence", sa.Column("reviewed_by", sa.String(length=120), nullable=True)
    )
    op.execute("UPDATE terms_evidence SET scope = applies_to")

    op.create_table(
        "commission_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column(
            "source_authority",
            sa.Enum(
                "OFFICIAL",
                "PARTNER_PORTAL",
                "WRITTEN_CONFIRMATION",
                "THIRD_PARTY",
                "UNKNOWN",
                name="sourceauthority",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "commission_type",
            sa.Enum(
                "ONE_TIME",
                "RECURRING_UNSPECIFIED",
                "RECURRING_LIMITED",
                "RECURRING_LIFETIME",
                "HYBRID",
                name="commissiontype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("commission_rate", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("rate_is_maximum", sa.Boolean(), nullable=False),
        sa.Column("applies_to", sa.String(length=120), nullable=False),
        sa.Column(
            "review_status",
            sa.Enum(
                "PROPOSED",
                "ACCEPTED",
                "REJECTED",
                name="evidencereviewstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("collected_by", sa.String(length=80), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_hash"),
    )
    op.create_index(
        "ix_commission_fact_program_checked",
        "commission_facts",
        ["program_id", "checked_at"],
        unique=False,
    )

    op.create_table(
        "terms_research_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("fixture_version", sa.String(length=80), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PROPOSAL_READY",
                "CONFLICT",
                "MANUAL_INPUT_REQUIRED",
                name="researchstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discovery_confidence", sa.Float(), nullable=False),
        sa.Column("source_urls", sa.JSON(), nullable=False),
        sa.Column("permission_proposals", sa.JSON(), nullable=False),
        sa.Column("imported_fact_ids", sa.JSON(), nullable=False),
        sa.Column("run_hash", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_hash"),
    )
    op.create_index(
        op.f("ix_terms_research_runs_domain"),
        "terms_research_runs",
        ["domain"],
        unique=False,
    )
    op.create_index(
        op.f("ix_terms_research_runs_program_id"),
        "terms_research_runs",
        ["program_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_terms_research_runs_program_id"), table_name="terms_research_runs"
    )
    op.drop_index(op.f("ix_terms_research_runs_domain"), table_name="terms_research_runs")
    op.drop_table("terms_research_runs")
    op.drop_index("ix_commission_fact_program_checked", table_name="commission_facts")
    op.drop_table("commission_facts")
    with op.batch_alter_table("terms_evidence") as batch_op:
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("collected_by")
        batch_op.drop_column("source_authority")
        batch_op.drop_column("review_status")
        batch_op.drop_column("scope")
