from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "e91f4d7a2c18"
CURRENT_HEAD = "4f7c2a91d5e0"


def _alembic(database: Path, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["AFI_OS_DATABASE_URL"] = f"sqlite:///{database}"
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_llm_terms_migration_round_trip_preserves_existing_data(tmp_path: Path) -> None:
    database = tmp_path / "llm-terms-migration.db"
    _alembic(database, "upgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO merchants (id,name,website_domain,created_at,updated_at) "
            "VALUES (1,'Keep','keep.example','2026-08-13','2026-08-13')"
        )
        connection.execute(
            "INSERT INTO programs (id,merchant_id,name,status,paid_search_permission,"
            "brand_keyword_permission,non_brand_permission,direct_link_permission,"
            "trademark_in_ad_copy_permission,required_negative_keywords,allowed_geos,"
            "blocked_geos,created_at,updated_at) VALUES "
            "(1,1,'Keep Program','DISCOVERED','NOT_CHECKED','NOT_CHECKED','NOT_CHECKED',"
            "'NOT_CHECKED','NOT_CHECKED','[]','[]','[]','2026-08-13','2026-08-13')"
        )

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT name FROM programs WHERE id=1").fetchone() == (
            "Keep Program",
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(commission_facts)")}
        assert {"commission_flat", "recurring_months"} <= columns
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            CURRENT_HEAD,
        )

    _alembic(database, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT name FROM programs WHERE id=1").fetchone() == (
            "Keep Program",
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='llm_extraction_runs'"
        ).fetchone() == (0,)
