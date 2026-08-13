from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

KEYCHAIN_SERVICE = "com.afi-os.advertiser"
API_KEY_LABEL = "api-key"


def _security_path() -> Path | None:
    path = Path("/usr/bin/security")
    return path if path.is_file() else None


def _validated(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 16384 or "\x00" in normalized:
        raise ValueError("SerpApi API key không hợp lệ")
    return normalized


def credential_present(*, runner: Callable = subprocess.run) -> bool:
    executable = _security_path()
    if executable is None:
        return False
    try:
        result = runner(
            [
                str(executable),
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                API_KEY_LABEL,
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
            API_KEY_LABEL,
            "-w",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Không đọc được SerpApi API key trong Keychain")
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
            API_KEY_LABEL,
            "-w",
        ],
        input=f"{normalized}\n{normalized}\n",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
        start_new_session=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Không lưu được SerpApi API key vào Keychain")


def advertiser_provider_readiness(
    *, presence_checker: Callable[[], bool] = credential_present
) -> dict:
    ready = bool(presence_checker())
    return {
        "status": "READY" if ready else "CONNECTION_REQUIRED",
        "provider": "SERPAPI",
        "api_key_present": ready,
        "setup_command": "SETUP-ADVERTISER.command",
        "secret_exposed": False,
    }
