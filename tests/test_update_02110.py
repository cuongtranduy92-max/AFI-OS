from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

UPDATER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_02110_tool.py"
SPEC = importlib.util.spec_from_file_location("update_02110_tool", UPDATER_PATH)
assert SPEC is not None and SPEC.loader is not None
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


def _manifest_entry(payload: Path, relative: str) -> dict[str, object]:
    source = payload / relative
    return {
        "path": relative,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "size_bytes": source.stat().st_size,
        "mode": "0644",
    }


def test_updater_install_and_rollback_preserve_database(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "AFI-OS"
    source_root = Path(__file__).resolve().parents[1]
    (target / "src/afi_os").mkdir(parents=True)
    (target / "data").mkdir()
    (target / "backups").mkdir()
    shutil.copy2(source_root / "alembic.ini", target / "alembic.ini")
    shutil.copytree(source_root / "migrations", target / "migrations")
    (target / "pyproject.toml").write_text(
        '[project]\nname = "afi-os"\nversion = "0.2.109"\n', encoding="utf-8"
    )
    (target / "src/afi_os/__init__.py").write_text(
        '__version__ = "0.2.109"\n', encoding="utf-8"
    )
    with sqlite3.connect(target / "data/afi_os.db") as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES ('71e4a2b890c3')")
        connection.execute("CREATE TABLE preserved_rows (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO preserved_rows(value) VALUES ('keep-me')")

    payload = tmp_path / "payload"
    (payload / "src/afi_os").mkdir(parents=True)
    (payload / "src/afi_os/__init__.py").write_text(
        '__version__ = "0.2.110"\n', encoding="utf-8"
    )
    manifest_path = tmp_path / "payload-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "update_version": "0.2.110",
                "allowed_from_versions": ["0.2.109"],
                "expected_migration_head": "82c6d4f1a9b7",
                "files": [_manifest_entry(payload, "src/afi_os/__init__.py")],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        updater,
        "stop_application",
        lambda _target: {"status": "TEST", "launchd_labels": []},
    )
    monkeypatch.setattr(
        updater,
        "restore_launchd_services",
        lambda _target, labels: {"status": "TEST", "labels": labels},
    )

    def fake_upgrade(_target, database, _log):
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE alembic_version SET version_num = '82c6d4f1a9b7'")
        return {"command": ["test-alembic", "upgrade", "head"], "returncode": 0}

    monkeypatch.setattr(updater, "run_alembic_upgrade", fake_upgrade)

    backup = updater.install_update(target, manifest_path, payload)

    assert updater.installed_version(target) == "0.2.110"
    with sqlite3.connect(target / "data/afi_os.db") as connection:
        assert connection.execute("SELECT value FROM preserved_rows").fetchone() == (
            "keep-me",
        )
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    updater.rollback_update(target, backup)

    assert updater.installed_version(target) == "0.2.109"
    with sqlite3.connect(target / "data/afi_os.db") as connection:
        assert connection.execute("SELECT value FROM preserved_rows").fetchone() == (
            "keep-me",
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
