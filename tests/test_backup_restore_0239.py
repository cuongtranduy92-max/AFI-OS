from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from afi_os.services import backups

CURRENT_HEAD = "b84d0e26c104"


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
    value: str = "value",
    broken_foreign_key: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (head,))
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records VALUES (?)", (value,))
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children "
            "(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id))"
        )
        if broken_foreign_key:
            connection.execute("INSERT INTO children VALUES (1, 999)")


def _add_backup(
    root: Path,
    name: str,
    *,
    head: str = CURRENT_HEAD,
    value: str,
    created_at: str,
    broken_foreign_key: bool = False,
    expected_sha: str | None = None,
) -> Path:
    folder = root / "backups" / name
    database = folder / "afi_os.db"
    _write_database(
        database,
        head=head,
        value=value,
        broken_foreign_key=broken_foreign_key,
    )
    manifest = {
        "name": name,
        "created_at": created_at,
        "size_bytes": database.stat().st_size,
        "sha256": expected_sha or backups.sha256_file(database),
        "database_file": str(database),
        "version": "test",
        "alembic_versions": [head],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return database


def _record_value(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("SELECT value FROM records").fetchone()[0])


def test_create_backup_records_schema_integrity_and_foreign_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_database(database, value="live")

    result = backups.create_backup(prefix="manual")

    assert result["alembic_versions"] == [CURRENT_HEAD]
    assert result["integrity_check"] == "ok"
    assert result["foreign_key_check"] == "ok"
    assert len(result["sha256"]) == 64
    assert Path(result["database_file"]).is_file()


def test_create_backup_rejects_wrong_source_schema_and_removes_partial_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_database(database, head="wrong-schema", value="live")

    with pytest.raises(RuntimeError, match="schema database nguồn"):
        backups.create_backup(prefix="scheduled")

    assert not (tmp_path / "backups").exists() or not list(
        (tmp_path / "backups").iterdir()
    )


def test_create_backup_does_not_create_a_missing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="database nguồn không tồn tại"):
        backups.create_backup(prefix="scheduled")

    assert not database.exists()


def test_restore_skips_newer_wrong_schema_and_creates_emergency_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_database(database, value="live")
    compatible = _add_backup(
        tmp_path,
        "manual-compatible",
        value="restored",
        created_at="2026-08-10T00:00:00+00:00",
    )
    _add_backup(
        tmp_path,
        "manual-newer-wrong-schema",
        head="future-schema",
        value="wrong",
        created_at="2026-08-11T00:00:00+00:00",
    )

    result = backups.restore_latest()

    assert result["restored"]["database_file"] == str(compatible)
    assert _record_value(database) == "restored"
    assert result["emergency_backup"]["name"].startswith("emergency-before-restore-")
    assert _record_value(Path(result["emergency_backup"]["database_file"])) == "live"


def test_restore_rejects_bad_sha_and_foreign_keys_without_touching_live_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _configure(monkeypatch, tmp_path)
    _write_database(database, value="live")
    _add_backup(
        tmp_path,
        "manual-bad-sha",
        value="bad-sha",
        created_at="2026-08-11T00:00:00+00:00",
        expected_sha="0" * 64,
    )
    _add_backup(
        tmp_path,
        "manual-broken-foreign-key",
        value="bad-fk",
        created_at="2026-08-10T00:00:00+00:00",
        broken_foreign_key=True,
    )

    with pytest.raises(RuntimeError, match="Không có backup toàn vẹn tương thích"):
        backups.restore_latest()

    assert _record_value(database) == "live"
    assert not list((tmp_path / "backups").glob("emergency-before-restore-*"))


def test_update_backup_manifest_exposes_actual_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, tmp_path)
    folder = tmp_path / "backups" / "update-0.2.38-test"
    database = folder / "afi_os.db"
    _write_database(database, value="old")
    (folder / "update-manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-08-11T00:00:00+00:00",
                "update_version": "0.2.38",
                "database": {
                    "sha256": backups.sha256_file(database),
                    "alembic_versions": [CURRENT_HEAD],
                },
            }
        ),
        encoding="utf-8",
    )

    item = backups.list_backups()[0]

    assert item["version"] == "pre-update-0.2.38"
    assert item["alembic_versions"] == [CURRENT_HEAD]
    assert item["database_status"] == "OK"
