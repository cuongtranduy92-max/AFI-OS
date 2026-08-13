from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from afi_os.services import backups

HEAD = "a73c9e15b642"


def _configure(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    database = root / "data" / "afi_os.db"
    monkeypatch.setattr(
        backups,
        "get_settings",
        lambda: SimpleNamespace(
            project_root=root,
            database_url=f"sqlite:///{database}",
        ),
    )
    return database


def _write_migration(root: Path, head: str = HEAD) -> None:
    path = root / "migrations" / "versions" / "head.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        f'revision: str = "{head}"\ndown_revision = None\n',
        encoding="utf-8",
    )


def _write_backup(root: Path, *, value: str = "restored") -> Path:
    folder = root / "backups" / "manual-compatible"
    database = folder / "afi_os.db"
    folder.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (HEAD,))
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records VALUES (?)", (value,))
    manifest = {
        "name": folder.name,
        "created_at": "2026-08-11T00:00:00+00:00",
        "size_bytes": database.stat().st_size,
        "sha256": backups.sha256_file(database),
        "database_file": str(database),
        "version": "test",
        "alembic_versions": [HEAD],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return database


def test_expected_schema_heads_are_derived_from_migration_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, tmp_path)
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "one.py").write_text(
        'revision = "one"\ndown_revision = None\n', encoding="utf-8"
    )
    (versions / "two.py").write_text(
        'revision: str = "two"\ndown_revision: str | None = "one"\n',
        encoding="utf-8",
    )

    assert backups.expected_schema_heads() == ["two"]


def test_corrupt_live_database_can_restore_with_raw_emergency_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_migration(tmp_path)
    _write_backup(tmp_path)
    database.parent.mkdir(parents=True)
    database.write_bytes(b"corrupt-live-database")
    Path(f"{database}-wal").write_bytes(b"preserved-wal")
    Path(f"{database}-shm").write_bytes(b"preserved-shm")

    result = backups.restore_latest()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "restored"
    emergency = result["emergency_backup"]
    emergency_root = Path(emergency["database_file"]).parent
    assert emergency["kind"] == "AFI_OS_EMERGENCY_RAW_SNAPSHOT"
    assert Path(emergency["database_file"]).read_bytes() == b"corrupt-live-database"
    assert (emergency_root / "afi_os.db-wal.preserved").read_bytes() == b"preserved-wal"
    assert (emergency_root / "afi_os.db-shm.preserved").read_bytes() == b"preserved-shm"
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_corrupt_live_database_without_code_schema_stays_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_backup(tmp_path)
    database.parent.mkdir(parents=True)
    database.write_bytes(b"corrupt-live-database")

    with pytest.raises(RuntimeError, match="Không có backup toàn vẹn tương thích"):
        backups.restore_latest()

    assert database.read_bytes() == b"corrupt-live-database"
    assert not list((tmp_path / "backups").glob("emergency-before-restore-*"))
