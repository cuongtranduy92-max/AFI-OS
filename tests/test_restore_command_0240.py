from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@pytest.mark.parametrize("restore_status", [0, 9])
def test_restore_command_quiesces_and_restarts_launchd_even_on_failure(
    tmp_path: Path, restore_status: int
) -> None:
    target = tmp_path / "AFI-OS"
    target.mkdir()
    command = target / "RESTORE-LATEST-BACKUP.command"
    shutil.copy2(REPOSITORY_ROOT / command.name, command)
    command.chmod(0o755)
    log = tmp_path / "calls.log"
    fake_bin = tmp_path / "fake-bin"
    _executable(
        fake_bin / "launchctl",
        '#!/bin/sh\nprintf "launchctl:%s\\n" "$*" >> "$AFI_TEST_LOG"\nexit 0\n',
    )
    _executable(
        fake_bin / "curl",
        '#!/bin/sh\nif grep -q "bootstrap" "$AFI_TEST_LOG" 2>/dev/null; then\n'
        "  exit 0\nfi\nexit 1\n",
    )
    _executable(
        target / ".venv" / "bin" / "python",
        '#!/bin/sh\nprintf "python:%s\\n" "$*" >> "$AFI_TEST_LOG"\n'
        'exit "$AFI_TEST_RESTORE_STATUS"\n',
    )
    _executable(
        target / "STOP-AFI-OS.command",
        '#!/bin/sh\necho "stop" >> "$AFI_TEST_LOG"\n',
    )
    _executable(
        target / "START-AFI-OS.command",
        '#!/bin/sh\necho "start" >> "$AFI_TEST_LOG"\n',
    )
    environment = os.environ.copy()
    environment.update(
        {
            "AFI_OS_ASSUME_YES": "1",
            "AFI_OS_NONINTERACTIVE": "1",
            "AFI_OS_SKIP_OPEN": "1",
            "AFI_TEST_LOG": str(log),
            "AFI_TEST_RESTORE_STATUS": str(restore_status),
            "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        }
    )

    result = subprocess.run(
        ["bash", str(command)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == restore_status
    calls = log.read_text(encoding="utf-8")
    assert "bootout gui/" in calls
    assert "com.afi-os.server" in calls
    assert "com.afi-os.maintenance" in calls
    assert "python:-m afi_os.backup_cli restore-latest" in calls
    assert "bootstrap gui/" in calls
    assert "kickstart -k gui/" in calls
    assert calls.index("bootout gui/") < calls.index("python:-m")
    assert calls.index("python:-m") < calls.index("bootstrap gui/")
    if restore_status:
        assert "Restore không hoàn tất" in result.stdout
    else:
        assert "Restore hoàn tất; dịch vụ đã chạy lại" in result.stdout
