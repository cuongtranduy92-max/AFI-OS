from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import SyncStatus
from afi_os.maintenance import backup_is_due
from afi_os.models import SyncRun
from afi_os.schemas import BackupInfo
from afi_os.services import backups
from afi_os.services.runtime_status import runtime_status

CURRENT_HEAD = "a73c9e15b642"


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _configure(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    database = root / "data" / "afi_os.db"
    settings = SimpleNamespace(
        project_root=root,
        database_url=f"sqlite:///{database}",
    )
    monkeypatch.setattr(backups, "get_settings", lambda: settings)
    monkeypatch.setattr(backups, "expected_schema_heads", lambda: [CURRENT_HEAD])
    return database


def _write_database(
    path: Path,
    *,
    head: str = CURRENT_HEAD,
    broken_foreign_key: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (head,))
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records VALUES ('preserve')")
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children "
            "(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id))"
        )
        if broken_foreign_key:
            connection.execute("INSERT INTO children VALUES (1, 999)")


def _backup_folder(
    root: Path,
    name: str,
    *,
    head: str = CURRENT_HEAD,
    declared_head: str | None = None,
    broken_foreign_key: bool = False,
) -> Path:
    folder = root / "backups" / name
    database = folder / "afi_os.db"
    _write_database(database, head=head, broken_foreign_key=broken_foreign_key)
    manifest = {
        "name": name,
        "created_at": datetime.now(UTC).isoformat(),
        "size_bytes": database.stat().st_size,
        "sha256": backups.sha256_file(database),
        "database_file": str(database),
        "version": "test",
        "alembic_versions": [declared_head or head],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def test_created_backup_is_immediately_reported_as_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_database(database)

    created = backups.create_backup(prefix="manual")

    assert created["database_status"] == "OK"
    assert BackupInfo(**created).database_status == "OK"
    listed = backups.list_backups()
    assert len(listed) == 1
    assert listed[0]["database_status"] == "OK"
    assert listed[0]["sha256"] == created["sha256"]


def test_changed_backup_is_checksum_mismatch_and_does_not_delay_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, tmp_path)
    folder = _backup_folder(tmp_path, "scheduled-changed")
    with sqlite3.connect(folder / "afi_os.db") as connection:
        connection.execute("INSERT INTO records VALUES ('changed after manifest')")

    item = backups.list_backups()[0]

    assert item["database_status"] == "CHECKSUM_MISMATCH"
    assert backup_is_due([item], datetime.now(UTC)) is True


def test_foreign_key_and_declared_schema_failures_are_not_reported_as_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, tmp_path)
    _backup_folder(
        tmp_path,
        "scheduled-broken-foreign-key",
        broken_foreign_key=True,
    )
    _backup_folder(
        tmp_path,
        "scheduled-wrong-schema",
        declared_head="future-head",
    )

    by_name = {item["name"]: item for item in backups.list_backups()}

    assert (
        by_name["scheduled-broken-foreign-key"]["database_status"]
        == "FOREIGN_KEY_ERROR"
    )
    assert by_name["scheduled-wrong-schema"]["database_status"] == "SCHEMA_MISMATCH"


def test_internally_consistent_future_schema_is_not_safe_for_current_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(backups, "expected_schema_heads", lambda: [CURRENT_HEAD])
    _backup_folder(
        tmp_path,
        "scheduled-future-schema",
        head="future-head",
    )

    item = backups.list_backups()[0]

    assert item["database_status"] == "SCHEMA_MISMATCH"


def test_unreadable_database_remains_visible_as_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, tmp_path)
    folder = tmp_path / "backups" / "scheduled-invalid"
    folder.mkdir(parents=True)
    database = folder / "afi_os.db"
    database.write_bytes(b"not a sqlite database")
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "name": folder.name,
                "created_at": datetime.now(UTC).isoformat(),
                "sha256": backups.sha256_file(database),
                "alembic_versions": [CURRENT_HEAD],
            }
        ),
        encoding="utf-8",
    )

    item = backups.list_backups()[0]

    assert item["database_status"] == "INVALID"
    assert item["alembic_versions"] == []


def test_runtime_uses_latest_verified_backup_and_flags_when_none_is_safe() -> None:
    now = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="AFI_OS_MAINTENANCE",
                started_at=now - timedelta(minutes=10),
                ended_at=now - timedelta(minutes=9),
                status=SyncStatus.SUCCESS,
                rows_read=0,
                rows_written=0,
                metadata_json={},
            )
        )
        db.commit()

    valid = {
        "name": "scheduled-valid",
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "size_bytes": 123,
        "database_status": "OK",
    }
    invalid = {
        "name": "scheduled-invalid",
        "created_at": (now - timedelta(minutes=5)).isoformat(),
        "size_bytes": 456,
        "database_status": "CHECKSUM_MISMATCH",
    }
    with SessionLocal() as db:
        recovered = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [invalid, valid],
        )
        unsafe = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [invalid],
        )

    assert recovered["status"] == "HEALTHY"
    assert recovered["latest_scheduled_backup_name"] == "scheduled-valid"
    assert recovered["scheduled_backup_due"] is False
    assert recovered["scheduled_backup_invalid_count"] == 1
    assert unsafe["status"] == "ATTENTION"
    assert unsafe["latest_scheduled_backup_name"] is None
    assert unsafe["scheduled_backup_due"] is True
    assert unsafe["next_backup_due_at"] == now
