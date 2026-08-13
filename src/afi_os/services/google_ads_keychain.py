from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

KEYCHAIN_SERVICE = "com.afi-os.google-ads"
CORE_CREDENTIAL_LABELS = (
    "developer-token",
    "oauth-client-id",
    "oauth-client-secret",
    "refresh-token",
)
OPTIONAL_CREDENTIAL_LABELS = ("login-customer-id",)
ALLOWED_CREDENTIAL_LABELS = CORE_CREDENTIAL_LABELS + OPTIONAL_CREDENTIAL_LABELS


def _security_path() -> Path | None:
    path = Path("/usr/bin/security")
    return path if path.is_file() else None


def _validated_value(label: str, value: str) -> str:
    if label not in ALLOWED_CREDENTIAL_LABELS:
        raise ValueError("Tên credential không được hỗ trợ")
    normalized = value.strip()
    if not normalized or len(normalized) > 16384 or "\x00" in normalized:
        raise ValueError("Giá trị credential không hợp lệ")
    return normalized


def credential_present(label: str) -> bool:
    executable = _security_path()
    if label not in ALLOWED_CREDENTIAL_LABELS or executable is None:
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


def store_credential(
    label: str,
    value: str,
    *,
    runner: Callable = subprocess.run,
) -> None:
    executable = _security_path()
    value = _validated_value(label, value)
    if executable is None:
        raise RuntimeError("macOS Keychain command không khả dụng")
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
        # `security ... -w` reads the password interactively and, when a new
        # item is created, asks for the same value a second time.  Supplying
        # both lines keeps the secret out of argv while working for both new
        # items and `-U` updates (an unused second line is harmless).
        input=f"{value}\n{value}\n",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
        # `security` may open the caller's controlling TTY instead of reading
        # the supplied stdin when this setup script is launched by double
        # click in Terminal.  A separate session removes that TTY so the
        # password and confirmation are consumed only from the private pipe.
        start_new_session=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Không lưu được credential {label} vào Keychain")


def delete_credential(
    label: str,
    *,
    runner: Callable = subprocess.run,
) -> None:
    executable = _security_path()
    if label not in ALLOWED_CREDENTIAL_LABELS:
        raise ValueError("Tên credential không được hỗ trợ")
    if executable is None:
        raise RuntimeError("macOS Keychain command không khả dụng")
    result = runner(
        [
            str(executable),
            "delete-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            label,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Không xóa được credential {label} khỏi Keychain")


def read_credential(
    label: str,
    *,
    runner: Callable = subprocess.run,
) -> str:
    executable = _security_path()
    if label not in ALLOWED_CREDENTIAL_LABELS:
        raise ValueError("Tên credential không được hỗ trợ")
    if executable is None:
        raise RuntimeError("macOS Keychain command không khả dụng")
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
        raise RuntimeError(f"Không đọc được credential {label} từ Keychain")
    return result.stdout.strip()


def replace_core_credentials_atomically(
    values: dict[str, str],
    *,
    presence_checker: Callable[[str], bool] = credential_present,
    credential_reader: Callable[[str], str] = read_credential,
    credential_writer: Callable[[str, str], None] = store_credential,
    credential_deleter: Callable[[str], None] = delete_credential,
) -> tuple[str, ...]:
    labels = tuple(label for label in ALLOWED_CREDENTIAL_LABELS if label in values)
    value_labels = set(values)
    allowed_sets = (
        set(CORE_CREDENTIAL_LABELS),
        set(CORE_CREDENTIAL_LABELS + OPTIONAL_CREDENTIAL_LABELS),
    )
    if value_labels not in allowed_sets:
        raise ValueError(
            "Bộ Google Ads credential phải có đủ bốn thành phần cốt lõi "
            "và chỉ được thêm Login Customer ID"
        )
    normalized = {
        label: _validated_value(label, values[label]) for label in labels
    }
    previous = {}
    for label in labels:
        if presence_checker(label):
            previous[label] = credential_reader(label)

    updated = []
    try:
        for label in labels:
            updated.append(label)
            credential_writer(label, normalized[label])
    except Exception as exc:
        rollback_errors = []
        for label in reversed(updated):
            try:
                if label in previous:
                    credential_writer(label, previous[label])
                elif presence_checker(label):
                    credential_deleter(label)
            except Exception as rollback_exc:
                rollback_errors.append(f"{label}: {type(rollback_exc).__name__}")
        if rollback_errors:
            raise RuntimeError(
                "Không lưu được bộ credential; Keychain rollback cần kiểm tra lại: "
                + ", ".join(rollback_errors)
            ) from exc
        raise RuntimeError(
            "Không lưu được bộ credential; các giá trị Keychain trước đó đã được phục hồi"
        ) from exc
    return labels
