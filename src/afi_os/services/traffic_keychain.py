from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

KEYCHAIN_SERVICE = "com.afi-os.traffic-data"
SUPPORTED_PROVIDERS = {"SIMILARWEB", "SEMRUSH", "APIFY"}
ALLOWED_LABELS = ("provider", "api-key")


def _security_path() -> Path | None:
    path = Path("/usr/bin/security")
    return path if path.is_file() else None


def _validated(label: str, value: str) -> str:
    if label not in ALLOWED_LABELS:
        raise ValueError("Tên traffic credential không được hỗ trợ")
    normalized = value.strip()
    if not normalized or len(normalized) > 16384 or "\x00" in normalized:
        raise ValueError("Giá trị traffic credential không hợp lệ")
    if label == "provider":
        normalized = normalized.upper()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError("Provider phải là SIMILARWEB, SEMRUSH hoặc APIFY")
    return normalized


def credential_present(label: str) -> bool:
    executable = _security_path()
    if label not in ALLOWED_LABELS or executable is None:
        return False
    try:
        result = subprocess.run(
            [
                str(executable),
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                label,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def read_credential(label: str, *, runner: Callable = subprocess.run) -> str:
    executable = _security_path()
    if label not in ALLOWED_LABELS or executable is None:
        raise RuntimeError("macOS Keychain không khả dụng hoặc credential không hợp lệ")
    result = runner(
        [
            str(executable),
            "find-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            label,
            "-w",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Không đọc được traffic credential {label}")
    return _validated(label, result.stdout)


def store_credential(label: str, value: str, *, runner: Callable = subprocess.run) -> None:
    executable = _security_path()
    normalized = _validated(label, value)
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
            label,
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
        raise RuntimeError(f"Không lưu được traffic credential {label}")


def traffic_provider_readiness(
    *,
    presence_checker: Callable[[str], bool] = credential_present,
    credential_reader: Callable[[str], str] = read_credential,
) -> dict:
    present = {label: bool(presence_checker(label)) for label in ALLOWED_LABELS}
    provider = None
    if present["provider"]:
        try:
            provider = credential_reader("provider").upper()
        except (RuntimeError, ValueError):
            provider = None
    ready = bool(provider in SUPPORTED_PROVIDERS and present["api-key"])
    return {
        "status": "READY" if ready else "CONNECTION_REQUIRED",
        "provider": provider,
        "supported_providers": sorted(SUPPORTED_PROVIDERS),
        "api_key_present": present["api-key"],
        "setup_command": "SETUP-TRAFFIC-DATA.command",
        "secret_exposed": False,
    }
