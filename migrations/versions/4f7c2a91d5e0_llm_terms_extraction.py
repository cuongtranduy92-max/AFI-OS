"""LLM Terms extraction cache and operator-review proposals.

Revision ID: 4f7c2a91d5e0
Revises: e91f4d7a2c18
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f7c2a91d5e0"
down_revision: str | None = "e91f4d7a2c18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("commission_facts") as batch:
        batch.add_column(sa.Column("commission_flat", sa.Numeric(18, 6), nullable=True))
        batch.add_column(sa.Column("recurring_months", sa.Integer(), nullable=True))

    op.create_table(
        "llm_extraction_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("source_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rejected_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_extraction_runs_program_id", "llm_extraction_runs", ["program_id"])
    op.create_index("ix_llm_extraction_runs_domain", "llm_extraction_runs", ["domain"])
    op.create_index(
        "ix_llm_extraction_runs_content_hash",
        "llm_extraction_runs",
        ["content_hash"],
        unique=True,
    )

    op.create_table(
        "commercial_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_authority", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(length=16), nullable=False, server_default="PROPOSED"),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "collected_by",
            sa.String(length=80),
            nullable=False,
            server_default="ANTHROPIC_LLM",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope IN ('PACKAGES','PAYMENT')", name="ck_commercial_scope"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commercial_proposals_program_id", "commercial_proposals", ["program_id"])
    op.create_index("ix_commercial_proposals_scope", "commercial_proposals", ["scope"])
    op.create_index(
        "ix_commercial_proposals_proposal_hash",
        "commercial_proposals",
        ["proposal_hash"],
        unique=True,
    )
    op.create_index(
        "ix_commercial_program_status",
        "commercial_proposals",
        ["program_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_commercial_program_status", table_name="commercial_proposals")
    op.drop_index("ix_commercial_proposals_proposal_hash", table_name="commercial_proposals")
    op.drop_index("ix_commercial_proposals_scope", table_name="commercial_proposals")
    op.drop_index("ix_commercial_proposals_program_id", table_name="commercial_proposals")
    op.drop_table("commercial_proposals")

    op.drop_index("ix_llm_extraction_runs_content_hash", table_name="llm_extraction_runs")
    op.drop_index("ix_llm_extraction_runs_domain", table_name="llm_extraction_runs")
    op.drop_index("ix_llm_extraction_runs_program_id", table_name="llm_extraction_runs")
    op.drop_table("llm_extraction_runs")

    with op.batch_alter_table("commission_facts") as batch:
        batch.drop_column("recurring_months")
        batch.drop_column("commission_flat")
