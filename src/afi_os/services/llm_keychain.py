from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

KEYCHAIN_SERVICE = "com.afi-os.llm"
KEYCHAIN_ACCOUNT = "api-key"


def _security_path() -> Path | None:
    path = Path("/usr/bin/security")
    return path if path.is_file() else None


def _validated(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 16_384 or "\x00" in normalized:
        raise ValueError("Anthropic API key không hợp lệ")
    return normalized


def credential_present() -> bool:
    executable = _security_path()
    if executable is None:
        return False
    try:
        result = subprocess.run(
            [
                str(executable),
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def read_credential(*, runner: Callable = subprocess.run) -> str:
    executable = _security_path()
    if executable is None:
        raise RuntimeError("macOS Keychain không khả dụng")
    result = runner(
        [
            str(executable),
            "find-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Không đọc được Anthropic API key trong Keychain")
    return _validated(result.stdout)


def store_credential(value: str, *, runner: Callable = subprocess.run) -> None:
    executable = _security_path()
    normalized = _validated(value)
    if executable is None:
        raise RuntimeError("macOS Keychain không khả dụng")
    result = runner(
        [
            str(executable),
            "add-generic-password",
            "-U",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
        ],
        input=f"{normalized}\n{normalized}\n",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
        # Force ``security`` to consume the private stdin pipe instead of the
        # Terminal controlling TTY when SETUP-LLM.command is double-clicked.
        start_new_session=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Không lưu được Anthropic API key vào Keychain")


def llm_readiness(*, presence_checker: Callable[[], bool] = credential_present) -> dict:
    ready = bool(presence_checker())
    return {
        "status": "READY" if ready else "CONNECTION_REQUIRED",
        "provider": "ANTHROPIC",
        "api_key_present": ready,
        "setup_command": "SETUP-LLM.command",
        "secret_exposed": False,
    }
