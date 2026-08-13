"""Vietnamese summaries and translations for source-backed terms facts.

Revision ID: 71e4a2b890c3
Revises: 6b1d8e2c4108
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "71e4a2b890c3"
down_revision: str | None = "6b1d8e2c4108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("terms_evidence", "commission_facts", "commercial_proposals"):
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(sa.Column("summary_vi", sa.Text(), nullable=True))
            batch.add_column(sa.Column("quote_vi", sa.Text(), nullable=True))


def downgrade() -> None:
    for table_name in ("commercial_proposals", "commission_facts", "terms_evidence"):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_column("quote_vi")
            batch.drop_column("summary_vi")
