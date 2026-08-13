from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "d8a6f4b20317"
CURRENT_HEAD = "f21a58d9c341"


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


def test_migration_backfills_program_projects_and_round_trips(tmp_path: Path) -> None:
    database = tmp_path / "portfolio-migration.db"
    _alembic(database, "upgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO merchants (
                id, name, website_domain, legal_name, country, notes,
                created_at, updated_at
            ) VALUES (
                1, 'Migration Fixture', 'migration-0285.example', NULL, 'US', NULL,
                '2026-08-12T00:00:00+00:00', '2026-08-12T00:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO programs (
                id, merchant_id, network_id, name, signup_url, dashboard_url, status,
                paid_search_permission, brand_keyword_permission, non_brand_permission,
                direct_link_permission, trademark_in_ad_copy_permission,
                required_negative_keywords, allowed_geos, blocked_geos,
                last_terms_checked_at, terms_version, notes, created_at, updated_at
            ) VALUES (
                1, 1, NULL, 'Migration Affiliate Program',
                'https://migration-0285.example/partners', NULL, 'PAUSED',
                'NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED',
                'NOT_CHECKED', '[]', '[]', '[]', NULL, NULL, NULL,
                '2026-08-12T00:00:00+00:00', '2026-08-12T00:00:00+00:00'
            )
            """
        )

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )
        project = connection.execute(
            """
            SELECT domain, program_id, stage, registration_status, next_action
            FROM projects
            """
        ).fetchone()
        assert project == (
            "migration-0285.example",
            1,
            "PAUSED",
            "BLOCKED_REGISTRATION",
            "Kiểm tra lại khả năng đăng ký hoặc giữ PAUSED",
        )
        assert connection.execute("SELECT COUNT(*) FROM metric_snapshots").fetchone()[0] == 0

    _alembic(database, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM programs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        project_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        assert "stage" not in project_columns
        assert "registration_status" not in project_columns
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='metric_snapshots'"
            ).fetchone()[0]
            == 0
        )

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )
