from __future__ import annotations

import importlib.util
import plistlib
from pathlib import Path
from types import SimpleNamespace

UPDATER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_0299_tool.py"
SPEC = importlib.util.spec_from_file_location("update_0299_tool", UPDATER_PATH)
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
