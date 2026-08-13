from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PREVIOUS_HEAD = "71e4a2b890c3"
CURRENT_HEAD = "82c6d4f1a9b7"


def _alembic(database: Path, *arguments: str) -> None:
    env = {**os.environ, "AFI_OS_DATABASE_URL": f"sqlite:///{database}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_progressive_appraisal_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    database = tmp_path / "progressive.db"
    _alembic(database, "upgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        before_projects = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(appraisal_jobs)")
        }
        assert {
            "id",
            "project_id",
            "domain",
            "status",
            "per_source_json",
            "created_at",
            "finished_at",
        } <= columns
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == before_projects
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )

    _alembic(database, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        assert "appraisal_jobs" not in {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == before_projects
