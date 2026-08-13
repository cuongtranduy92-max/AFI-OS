from __future__ import annotations

import hashlib
import importlib.util
import json
import plistlib
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

UPDATER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_02104_tool.py"
SPEC = importlib.util.spec_from_file_location("update_02104_tool", UPDATER_PATH)
assert SPEC is not None and SPEC.loader is not None
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


def _write_plist(path: Path, target: Path) -> None:
    path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.afi-os.server",
                "WorkingDirectory": str(target),
            }
        )
    )


def test_loaded_launchd_services_only_returns_services_owned_by_target(
    tmp_path: Path, monkeypatch
) -> None:
    live_target = tmp_path / "live"
    other_target = tmp_path / "other"
    live_target.mkdir()
    other_target.mkdir()
    server_plist = tmp_path / "server.plist"
    maintenance_plist = tmp_path / "maintenance.plist"
    _write_plist(server_plist, live_target)
    _write_plist(maintenance_plist, live_target)

    paths = {
        "com.afi-os.server": server_plist,
        "com.afi-os.maintenance": maintenance_plist,
    }
    calls: list[list[str]] = []

    monkeypatch.setattr(updater, "launchd_plist_path", lambda label: paths[label])

    def fake_launchctl(arguments, check=True):
        calls.append(list(arguments))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(updater, "run_launchctl", fake_launchctl)

    assert updater.loaded_launchd_services(live_target) == list(updater.LAUNCHD_LABELS)
    assert len(calls) == 2

    calls.clear()
    assert updater.loaded_launchd_services(other_target) == []
    assert calls == []


def test_launchd_service_target_rejects_symlink_and_invalid_plist(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    invalid = tmp_path / "invalid.plist"
    invalid.write_text("not a plist", encoding="utf-8")

    monkeypatch.setattr(updater, "launchd_plist_path", lambda _label: invalid)
    assert updater.launchd_service_targets("com.afi-os.server", target) is False

    valid = tmp_path / "valid.plist"
    _write_plist(valid, target)
    linked = tmp_path / "linked.plist"
    linked.symlink_to(valid)
    monkeypatch.setattr(updater, "launchd_plist_path", lambda _label: linked)
    assert updater.launchd_service_targets("com.afi-os.server", target) is False


def _manifest_entry(payload: Path, relative: str) -> dict[str, object]:
    source = payload / relative
    return {
        "path": relative,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "size_bytes": source.stat().st_size,
        "mode": "0644",
    }


def test_install_and_rollback_preserve_database_and_version(
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
        '[project]\nname = "afi-os"\nversion = "0.2.103"\n', encoding="utf-8"
    )
    (target / "src/afi_os/__init__.py").write_text(
        '__version__ = "0.2.103"\n', encoding="utf-8"
    )
    with sqlite3.connect(target / "data/afi_os.db") as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES ('a73c9e15b642')")
        connection.execute("CREATE TABLE preserved_rows (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO preserved_rows(value) VALUES ('keep-me')")

    payload = tmp_path / "payload"
    (payload / "src/afi_os").mkdir(parents=True)
    (payload / "src/afi_os/__init__.py").write_text(
        '__version__ = "0.2.104"\n', encoding="utf-8"
    )
    manifest_path = tmp_path / "payload-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "update_version": "0.2.104",
                "allowed_from_versions": ["0.2.103"],
                "expected_migration_head": "b84d0e26c104",
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
            connection.execute("UPDATE alembic_version SET version_num = 'b84d0e26c104'")
        return {
            "command": ["test-alembic", "upgrade", "head"],
            "returncode": 0,
        }

    monkeypatch.setattr(updater, "run_alembic_upgrade", fake_upgrade)

    backup = updater.install_update(target, manifest_path, payload)

    assert updater.installed_version(target) == "0.2.104"
    with sqlite3.connect(target / "data/afi_os.db") as connection:
        assert connection.execute("SELECT value FROM preserved_rows").fetchone() == ("keep-me",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "b84d0e26c104",
        )
    installed_manifest = json.loads((backup / "update-manifest.json").read_text())
    assert installed_manifest["phase"] == "INSTALLED"
    assert installed_manifest["post_update_database"]["integrity_check"] == "ok"

    updater.rollback_update(target, backup)

    assert updater.installed_version(target) == "0.2.103"
    with sqlite3.connect(target / "data/afi_os.db") as connection:
        assert connection.execute("SELECT value FROM preserved_rows").fetchone() == ("keep-me",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    rolled_back_manifest = json.loads((backup / "update-manifest.json").read_text())
    assert rolled_back_manifest["phase"] == "ROLLED_BACK"
