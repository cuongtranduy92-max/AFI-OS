from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "b84d0e26c104"
CURRENT_HEAD = "e91f4d7a2c18"


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


def test_resource_migration_round_trip_preserves_existing_ads_account(
    tmp_path: Path,
) -> None:
    database = tmp_path / "resource-migration.db"
    _alembic(database, "upgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO ads_accounts (
                id, external_id, name, currency, status, time_zone,
                last_synced_at, created_at, updated_at
            ) VALUES (
                1, '3707342176', 'Existing Google Ads', 'USD', 'ENABLED', 'Asia/Bangkok',
                NULL, '2026-08-13T00:00:00+00:00', '2026-08-13T00:00:00+00:00'
            )
            """
        )

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        account = connection.execute(
            """
            SELECT external_id, name, resource_state, health, rent_cost, spend_fee_pct
            FROM ads_accounts WHERE id = 1
            """
        ).fetchone()
        assert account == ("3707342176", "Existing Google Ads", "CHAY", "OK", 0, 0)
        assert connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )

    _alembic(database, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT external_id, name FROM ads_accounts").fetchone() == (
            "3707342176",
            "Existing Google Ads",
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ads_accounts)")}
        assert "resource_state" not in columns
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='emails'"
        ).fetchone()[0] == 0

    _alembic(database, "upgrade", CURRENT_HEAD)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM ads_accounts").fetchone()[0] == 1
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == CURRENT_HEAD
        )
