from __future__ import annotations

import plistlib
from pathlib import Path

from scripts import launchd_manager


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "AFI-OS"
    for relative in (".venv/bin/python", "src/afi_os/main.py", "src/afi_os/maintenance.py"):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")
    return target


def test_maintenance_uses_wake_recoverable_calendar_slots(tmp_path: Path) -> None:
    maintenance = launchd_manager.build_plists(_target(tmp_path))[
        launchd_manager.MAINTENANCE_LABEL
    ]
    assert maintenance["StartCalendarInterval"] == [{"Minute": 0}, {"Minute": 30}]
    assert maintenance["RunAtLoad"] is True
    assert "StartInterval" not in maintenance


def test_calendar_schedule_round_trips_through_plist(tmp_path: Path) -> None:
    payload = launchd_manager.build_plists(_target(tmp_path))[
        launchd_manager.MAINTENANCE_LABEL
    ]
    output = tmp_path / "maintenance.plist"
    launchd_manager.write_plist(output, payload)
    with output.open("rb") as handle:
        restored = plistlib.load(handle)
    assert restored["StartCalendarInterval"] == [{"Minute": 0}, {"Minute": 30}]
