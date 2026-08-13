from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "f21a58d9c341"
CURRENT_HEAD = "a73c9e15b642"


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


def test_automation_queue_migration_round_trip_preserves_existing_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "automation-queue-migration.db"
    _alembic(database, "upgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO merchants (
                id, name, website_domain, legal_name, country, notes,
                created_at, updated_at
            ) VALUES (
                1, 'Queue Fixture', 'queue-migration.example', NULL, 'US', NULL,
                '2026-08-12T00:00:00+00:00', '2026-08-12T00:00:00+00:00'
            )
            """
        )

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM merchants").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM automation_jobs").fetchone()[0] == 0
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )

    _alembic(database, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM merchants").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='automation_jobs'"
        ).fetchone()[0] == 0
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == PREVIOUS_HEAD
        )

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM merchants").fetchone()[0] == 1
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )
