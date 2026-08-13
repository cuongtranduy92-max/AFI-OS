from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def test_backup_command_exits_successfully_in_noninteractive_mode(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    target = tmp_path / "AFI-OS"
    target.mkdir()
    command = target / "BACKUP-AFI-OS.command"
    shutil.copy2(repository / command.name, command)
    runtime = target / ".venv/bin/python"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    runtime.chmod(0o755)
    environment = os.environ.copy()
    environment["AFI_OS_NONINTERACTIVE"] = "1"

    result = subprocess.run(
        ["/bin/bash", str(command)],
        cwd=target,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "Backup thành công" in result.stdout


def test_backup_command_reports_failure_and_never_prints_success(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    target = tmp_path / "AFI-OS"
    target.mkdir()
    command = target / "BACKUP-AFI-OS.command"
    shutil.copy2(repository / command.name, command)
    runtime = target / ".venv/bin/python"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    runtime.chmod(0o755)
    environment = os.environ.copy()
    environment["AFI_OS_NONINTERACTIVE"] = "1"

    result = subprocess.run(
        ["/bin/bash", str(command)],
        cwd=target,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )

    assert result.returncode == 9
    assert "LỖI: Backup không được tạo" in result.stdout
    assert "Backup thành công" not in result.stdout
