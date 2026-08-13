#!/usr/bin/env python3
"""Transactional installer and rollback utility for AFI-OS 0.2.77.

The release package is expected to contain:

    UPDATE-AFI-OS-0.2.77.command
    update_0277_tool.py
    payload-manifest.json
    payload/<manifest-listed files>

Only Python's standard library is used so the utility can run with either the
AFI-OS virtual environment or a stock macOS Python 3 installation.
"""

from __future__ import print_function

import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path, PurePosixPath


UPDATE_VERSION = "0.2.77"
MANIFEST_FORMAT_VERSION = 1
BACKUP_MANIFEST_NAME = "update-manifest.json"
DEFAULT_DATABASE_PATH = "data/afi_os.db"
LAUNCHD_LABELS = ("com.afi-os.server", "com.afi-os.maintenance")
FORBIDDEN_PAYLOAD_ROOTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".venv",
    "backups",
    "data",
    "legacy",
    "logs",
    "outputs",
    "work",
}
FORBIDDEN_PAYLOAD_PARTS = {"__pycache__"}
VERSION_PATTERN = re.compile(r"__version__\s*=\s*['\"]([^'\"]+)['\"]")
HEAD_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class UpdateError(RuntimeError):
    """An expected safety or update failure."""


def announce(message):
    print("[AFI-OS] {0}".format(message), flush=True)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path):
    """Best-effort directory fsync after an atomic replace."""
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".{0}.{1}.tmp".format(path.name, os.getpid()))
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temporary), str(path))
    _fsync_directory(path.parent)


def load_json(path, description):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as exc:
        raise UpdateError("Không đọc được {0}: {1}".format(description, exc))
    if not isinstance(value, dict):
        raise UpdateError("{0} phải là một JSON object".format(description))
    return value


def normalized_relative_path(raw_path, allow_database=False):
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise UpdateError("Manifest chứa đường dẫn trống hoặc không hợp lệ")
    if "\\" in raw_path:
        raise UpdateError("Đường dẫn manifest phải dùng dấu '/': {0}".format(raw_path))
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise UpdateError("Đường dẫn manifest không an toàn: {0}".format(raw_path))
    normalized = str(path)
    first = path.parts[0]
    if not allow_database:
        if (
            first in FORBIDDEN_PAYLOAD_ROOTS
            or any(part in FORBIDDEN_PAYLOAD_PARTS for part in path.parts)
            or normalized.endswith((".pyc", ".pyo"))
            or normalized == ".env"
            or first == ".env"
        ):
            raise UpdateError("Payload không được chạm vào: {0}".format(normalized))
    return normalized


def _is_within(candidate, root):
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def safe_target_path(target, relative_path, allow_database=False):
    relative_path = normalized_relative_path(relative_path, allow_database=allow_database)
    target = Path(target).resolve()
    candidate = target.joinpath(*PurePosixPath(relative_path).parts)

    current = target
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise UpdateError("Từ chối đường dẫn symlink trong target: {0}".format(current))
    resolved_candidate = candidate.resolve(strict=False)
    if not _is_within(resolved_candidate, target):
        raise UpdateError("Đường dẫn thoát khỏi target: {0}".format(relative_path))
    return candidate


def parse_mode(raw_mode):
    if raw_mode is None:
        return 0o644
    try:
        if isinstance(raw_mode, str):
            mode = int(raw_mode, 8)
        else:
            mode = int(raw_mode)
    except (TypeError, ValueError):
        raise UpdateError("File mode không hợp lệ: {0}".format(raw_mode))
    if mode < 0 or mode > 0o777:
        raise UpdateError("File mode ngoài phạm vi an toàn: {0}".format(raw_mode))
    return mode


def expected_heads_from_manifest(manifest):
    raw = manifest.get("expected_migration_head")
    if isinstance(raw, str):
        heads = [raw]
    elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        heads = raw
    else:
        raise UpdateError("Manifest thiếu expected_migration_head hợp lệ")
    heads = sorted(set(head.strip() for head in heads if head.strip()))
    if not heads or any(not HEAD_PATTERN.match(head) for head in heads):
        raise UpdateError("expected_migration_head không hợp lệ")
    return heads


def validate_payload_manifest(manifest_path, payload_root):
    manifest_path = Path(manifest_path).expanduser().resolve()
    payload_root = Path(payload_root).expanduser().resolve()
    manifest = load_json(manifest_path, "payload manifest")

    if manifest.get("format_version") != MANIFEST_FORMAT_VERSION:
        raise UpdateError("Payload manifest format không được hỗ trợ")
    if manifest.get("update_version") != UPDATE_VERSION:
        raise UpdateError("Payload không phải bản AFI-OS {0}".format(UPDATE_VERSION))
    expected_heads_from_manifest(manifest)

    allowed_versions = manifest.get("allowed_from_versions", ["0.2.76"])
    if not isinstance(allowed_versions, list) or not allowed_versions:
        raise UpdateError("allowed_from_versions không hợp lệ")
    if any(not isinstance(item, str) or not item for item in allowed_versions):
        raise UpdateError("allowed_from_versions chứa giá trị không hợp lệ")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise UpdateError("Payload manifest không có danh sách files")

    entries = []
    seen = set()
    for raw_entry in raw_files:
        if not isinstance(raw_entry, dict):
            raise UpdateError("Mỗi phần tử files phải là một JSON object")
        relative = normalized_relative_path(raw_entry.get("path"))
        if relative in seen:
            raise UpdateError("Payload manifest lặp đường dẫn: {0}".format(relative))
        seen.add(relative)

        expected_hash = raw_entry.get("sha256")
        if (
            not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(char not in "0123456789abcdef" for char in expected_hash.lower())
        ):
            raise UpdateError("SHA-256 không hợp lệ cho {0}".format(relative))
        expected_hash = expected_hash.lower()

        source = payload_root.joinpath(*PurePosixPath(relative).parts)
        if source.is_symlink() or not source.is_file():
            raise UpdateError("Payload thiếu file thường: {0}".format(relative))
        if not _is_within(source.resolve(), payload_root):
            raise UpdateError("Payload file thoát khỏi payload root: {0}".format(relative))

        actual_size = source.stat().st_size
        declared_size = raw_entry.get("size_bytes")
        if declared_size is not None and int(declared_size) != actual_size:
            raise UpdateError("Kích thước payload sai: {0}".format(relative))
        actual_hash = sha256_file(source)
        if actual_hash != expected_hash:
            raise UpdateError("Checksum payload sai: {0}".format(relative))

        entries.append(
            {
                "path": relative,
                "sha256": expected_hash,
                "size_bytes": actual_size,
                "mode": parse_mode(raw_entry.get("mode")),
                "source": source,
            }
        )

    entries.sort(key=lambda item: item["path"])
    manifest["_entries"] = entries
    manifest["_manifest_path"] = manifest_path
    manifest["_manifest_sha256"] = sha256_file(manifest_path)
    manifest["_payload_root"] = payload_root
    return manifest


def validate_target(raw_target):
    target = Path(raw_target).expanduser()
    if target.is_symlink():
        raise UpdateError("Target AFI-OS không được là symlink")
    target = target.resolve()
    if not target.is_dir():
        raise UpdateError("Không tìm thấy thư mục AFI-OS: {0}".format(target))
    required = ["alembic.ini", "pyproject.toml", "src/afi_os/__init__.py", "data/afi_os.db"]
    for relative in required:
        path = safe_target_path(target, relative, allow_database=relative.startswith("data/"))
        if not path.is_file() or path.is_symlink():
            raise UpdateError("Target thiếu file bắt buộc: {0}".format(relative))
    return target


def installed_version(target):
    version_file = safe_target_path(target, "src/afi_os/__init__.py")
    try:
        content = version_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise UpdateError("Không đọc được version hiện tại: {0}".format(exc))
    match = VERSION_PATTERN.search(content)
    if not match:
        raise UpdateError("Không xác định được version AFI-OS hiện tại")
    return match.group(1)


def process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        raise UpdateError("Không có quyền kiểm tra process PID {0}".format(pid))


def process_command(pid):
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("Không xác minh được process AFI-OS: {0}".format(exc))
    if result.returncode != 0:
        raise UpdateError("Không xác minh được command của PID {0}".format(pid))
    return result.stdout.strip()


def configured_local_port(target):
    raw_port = os.environ.get("AFI_OS_PORT")
    env_file = Path(target) / ".env"
    if raw_port is None and env_file.is_file() and not env_file.is_symlink():
        try:
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip().upper() == "AFI_OS_PORT":
                    raw_port = value.strip().strip("'\"")
                    break
        except OSError:
            pass
    try:
        port = int(raw_port) if raw_port is not None else 8765
    except ValueError:
        port = 8765
    return port if 1 <= port <= 65535 else 8765


def local_afi_os_is_responding(target):
    connection = http.client.HTTPConnection(
        "127.0.0.1", configured_local_port(target), timeout=0.4
    )
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        body = response.read(4096)
        if response.status != 200:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        return isinstance(payload, dict) and payload.get("status") == "ok"
    except OSError:
        return False
    finally:
        connection.close()


def launchd_domain():
    return "gui/{0}".format(os.getuid())


def launchd_plist_path(label):
    return Path.home() / "Library" / "LaunchAgents" / (label + ".plist")


def run_launchctl(arguments, check=True):
    executable = shutil.which("launchctl")
    if not executable:
        if check:
            raise UpdateError("Không tìm thấy launchctl để quản lý chế độ 24/7")
        return None
    result = subprocess.run(
        [executable] + list(arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise UpdateError(
            "launchctl {0} thất bại: {1}".format(
                " ".join(arguments), result.stdout.strip()
            )
        )
    return result


def loaded_launchd_services():
    loaded = []
    domain = launchd_domain()
    for label in LAUNCHD_LABELS:
        result = run_launchctl(["print", "{0}/{1}".format(domain, label)], check=False)
        if result is not None and result.returncode == 0:
            loaded.append(label)
    return loaded


def pause_launchd_services(target, wait_seconds=15):
    loaded = loaded_launchd_services()
    if not loaded:
        return []
    announce("Đang tạm dừng dịch vụ AFI-OS 24/7…")
    domain = launchd_domain()
    for label in loaded:
        run_launchctl(["bootout", "{0}/{1}".format(domain, label)])
    if "com.afi-os.server" in loaded:
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline and local_afi_os_is_responding(target):
            time.sleep(0.2)
        if local_afi_os_is_responding(target):
            raise UpdateError("Dịch vụ 24/7 chưa dừng; không bắt đầu cập nhật")
    return loaded


def restore_launchd_services(target, labels):
    labels = [label for label in labels if label in LAUNCHD_LABELS]
    if not labels:
        return {"status": "NOT_PREVIOUSLY_LOADED", "labels": []}

    manager = safe_target_path(target, "scripts/launchd_manager.py")
    if not manager.exists():
        removed = []
        for label in labels:
            path = launchd_plist_path(label)
            if path.is_file() and not path.is_symlink():
                path.unlink()
                removed.append(str(path))
        announce("Bản đã khôi phục chưa hỗ trợ 24/7; dịch vụ vẫn được tắt an toàn.")
        return {"status": "UNSUPPORTED_BY_RESTORED_VERSION", "labels": [], "removed": removed}

    if set(labels) == set(LAUNCHD_LABELS):
        runtime_python = target / ".venv/bin/python"
        if not runtime_python.is_file() or not os.access(str(runtime_python), os.X_OK):
            runtime_python = Path(sys.executable)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(target / "src") + os.pathsep + environment.get(
            "PYTHONPATH", ""
        )
        try:
            result = subprocess.run(
                [
                    str(runtime_python),
                    str(manager),
                    "install",
                    "--target",
                    str(target),
                ],
                cwd=str(target),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError("Không tái tạo được LaunchAgent từ code vừa cài") from exc
        if result.returncode != 0:
            tail = "\n".join((result.stdout or "").splitlines()[-12:])
            raise UpdateError("Tái tạo LaunchAgent thất bại:\n{0}".format(tail))
        announce("Đã tái tạo và khởi động lại dịch vụ AFI-OS 24/7 từ code hiện tại.")
        return {"status": "RESTORED", "labels": labels, "plist_regenerated": True}

    domain = launchd_domain()
    for label in labels:
        path = launchd_plist_path(label)
        if not path.is_file() or path.is_symlink():
            raise UpdateError("Thiếu LaunchAgent hợp lệ: {0}".format(path))
        run_launchctl(["bootout", domain, str(path)], check=False)
        run_launchctl(["bootstrap", domain, str(path)])
        run_launchctl(["enable", "{0}/{1}".format(domain, label)])
    if "com.afi-os.server" in labels:
        run_launchctl(["kickstart", "-k", "{0}/com.afi-os.server".format(domain)])
    announce("Đã khởi động lại dịch vụ AFI-OS 24/7.")
    return {"status": "RESTORED", "labels": labels}


def stop_application(target, wait_seconds=15):
    launchd_labels = pause_launchd_services(target, wait_seconds=wait_seconds)
    pid_file = safe_target_path(target, "logs/afi-os.pid", allow_database=True)
    if not pid_file.exists():
        if local_afi_os_is_responding(target):
            raise UpdateError(
                "AFI-OS đang chạy nhưng không có PID file; hãy đóng app trước khi update"
            )
        if launchd_labels:
            announce("Dịch vụ 24/7 đã dừng; tiếp tục cập nhật.")
            return {"status": "LAUNCHD_STOPPED", "launchd_labels": launchd_labels}
        announce("Ứng dụng hiện không có PID file; tiếp tục cập nhật.")
        return {"status": "NO_PID_FILE", "launchd_labels": []}
    try:
        raw_pid = pid_file.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
    except (OSError, ValueError):
        raise UpdateError("PID file không hợp lệ; không dừng process mơ hồ")
    if pid <= 1:
        raise UpdateError("PID trong logs/afi-os.pid không an toàn")

    if not process_exists(pid):
        pid_file.unlink()
        if local_afi_os_is_responding(target):
            raise UpdateError(
                "AFI-OS vẫn đang chạy bằng process khác; hãy đóng app trước khi update"
            )
        announce("Đã dọn PID file cũ.")
        return {"status": "STALE_PID", "pid": pid, "launchd_labels": launchd_labels}

    command = process_command(pid)
    markers = ("afi_os.main:app", "afi_os.cli", "afi-os")
    if not any(marker in command for marker in markers):
        raise UpdateError(
            "PID file trỏ tới process không giống AFI-OS; từ chối dừng: {0}".format(command)
        )
    announce("Đang dừng AFI-OS an toàn (PID {0})…".format(pid))
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not process_exists(pid):
            break
        time.sleep(0.2)
    if process_exists(pid):
        raise UpdateError(
            "AFI-OS chưa dừng sau {0} giây; không bắt đầu cập nhật".format(wait_seconds)
        )
    pid_file.unlink(missing_ok=True)
    if local_afi_os_is_responding(target):
        raise UpdateError("AFI-OS vẫn trả lời health check sau khi dừng; hủy update")
    return {
        "status": "STOPPED",
        "pid": pid,
        "command": command,
        "launchd_labels": launchd_labels,
    }


def sqlite_quote_identifier(identifier):
    return '"{0}"'.format(identifier.replace('"', '""'))


def database_observations(connection):
    integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity_rows != ["ok"]:
        raise UpdateError("SQLite integrity_check thất bại: {0}".format(integrity_rows[:5]))
    foreign_key_rows = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
    if foreign_key_rows:
        raise UpdateError("SQLite foreign_key_check phát hiện lỗi")

    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    row_counts = {}
    for table in tables:
        query = "SELECT COUNT(*) FROM {0}".format(sqlite_quote_identifier(table))
        row_counts[table] = int(connection.execute(query).fetchone()[0])

    alembic_versions = []
    if "alembic_version" in tables:
        alembic_versions = sorted(
            str(row[0]) for row in connection.execute("SELECT version_num FROM alembic_version")
        )
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    return {
        "integrity_check": "ok",
        "foreign_key_check": "ok",
        "journal_mode": journal_mode,
        "alembic_versions": alembic_versions,
        "row_counts": row_counts,
    }


def connect_database(path):
    connection = sqlite3.connect(str(path), timeout=30)
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def create_database_backup(database_path, destination):
    database_path = Path(database_path)
    destination = Path(destination)
    if not database_path.is_file() or database_path.is_symlink():
        raise UpdateError("Database nguồn không phải file thường")
    if destination.exists():
        raise UpdateError("File backup database đã tồn tại: {0}".format(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)

    original_mode = stat.S_IMODE(database_path.stat().st_mode)
    source = connect_database(database_path)
    try:
        before = database_observations(source)
        checkpoint = list(source.execute("PRAGMA wal_checkpoint(FULL)").fetchone())
        if checkpoint and int(checkpoint[0]) != 0:
            raise UpdateError("Không checkpoint được SQLite WAL; database vẫn đang bận")
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
    finally:
        source.close()

    os.chmod(destination, original_mode)
    with closing(connect_database(destination)) as copied:
        copied_observations = database_observations(copied)
    if copied_observations["row_counts"] != before["row_counts"]:
        raise UpdateError("Backup SQLite không giữ nguyên row counts")
    if copied_observations["alembic_versions"] != before["alembic_versions"]:
        raise UpdateError("Backup SQLite không giữ nguyên Alembic version")

    return {
        "path": DEFAULT_DATABASE_PATH,
        "backup_file": destination.name,
        "sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
        "mode": format(original_mode, "04o"),
        "wal_checkpoint": checkpoint,
        "integrity_check": copied_observations["integrity_check"],
        "foreign_key_check": copied_observations["foreign_key_check"],
        "journal_mode": before["journal_mode"],
        "alembic_versions": before["alembic_versions"],
        "row_counts": before["row_counts"],
    }


def create_unique_backup_directory(target, prefix):
    backup_root = safe_target_path(target, "backups", allow_database=True)
    if backup_root.is_symlink():
        raise UpdateError("backups/ không được là symlink")
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = backup_root / "{0}-{1}".format(prefix, stamp)
    suffix = 1
    while candidate.exists():
        candidate = backup_root / "{0}-{1}-{2}".format(prefix, stamp, suffix)
        suffix += 1
    candidate.mkdir(mode=0o700)
    return candidate


def snapshot_target_files(target, backup_directory, relative_paths):
    records = []
    for raw_relative in sorted(set(relative_paths)):
        relative = normalized_relative_path(raw_relative)
        destination = safe_target_path(target, relative)
        existed = destination.exists() or destination.is_symlink()
        record = {"path": relative, "existed": existed}
        if existed:
            if destination.is_symlink() or not destination.is_file():
                raise UpdateError("Target payload không phải file thường: {0}".format(relative))
            backup_file = backup_directory.joinpath("files", *PurePosixPath(relative).parts)
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(destination), str(backup_file))
            record.update(
                {
                    "backup_file": str(PurePosixPath("files") / PurePosixPath(relative)),
                    "sha256": sha256_file(backup_file),
                    "size_bytes": backup_file.stat().st_size,
                    "mode": format(stat.S_IMODE(destination.stat().st_mode), "04o"),
                }
            )
        records.append(record)
    return records


def atomic_copy_file(source, destination, mode):
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(".{0}.{1}.update-tmp".format(destination.name, os.getpid()))
    try:
        shutil.copyfile(str(source), str(temporary))
        os.chmod(temporary, mode)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(destination))
        _fsync_directory(destination.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def copy_payload(target, entries):
    for entry in entries:
        destination = safe_target_path(target, entry["path"])
        atomic_copy_file(entry["source"], destination, entry["mode"])
        if sha256_file(destination) != entry["sha256"]:
            raise UpdateError("Checksum sau khi cài sai: {0}".format(entry["path"]))


def database_url_for(path):
    return "sqlite:///{0}".format(Path(path).resolve())


def run_alembic_upgrade(target, database_path, log_path, timeout_seconds=180):
    alembic = safe_target_path(target, ".venv/bin/alembic", allow_database=True)
    if alembic.is_file() and os.access(str(alembic), os.X_OK):
        command = [str(alembic), "upgrade", "head"]
    else:
        # A normal venv often exposes ``bin/python`` as a symlink. Do not inspect
        # that fallback unless the regular Alembic launcher is unavailable; the
        # primary path above is sufficient for the bundled AFI-OS runtime.
        python = safe_target_path(target, ".venv/bin/python", allow_database=True)
        if python.is_file() and os.access(str(python), os.X_OK):
            command = [str(python), "-m", "alembic", "upgrade", "head"]
        else:
            raise UpdateError("Target thiếu Alembic runtime trong .venv")

    environment = os.environ.copy()
    environment["AFI_OS_DATABASE_URL"] = database_url_for(database_path)
    environment["PYTHONPATH"] = str(target / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            command,
            cwd=str(target),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        Path(log_path).write_text(str(output), encoding="utf-8")
        raise UpdateError("Alembic migration quá thời gian cho phép")
    except OSError as exc:
        raise UpdateError("Không chạy được Alembic: {0}".format(exc))

    Path(log_path).write_text(result.stdout or "", encoding="utf-8")
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-12:])
        raise UpdateError("Alembic migration thất bại:\n{0}".format(tail))
    return {"returncode": result.returncode, "log_file": Path(log_path).name}


def observe_database(database_path):
    with closing(connect_database(database_path)) as connection:
        return database_observations(connection)


def verify_updated_database(database_path, database_before, expected_heads):
    after = observe_database(database_path)
    if after["alembic_versions"] != sorted(expected_heads):
        raise UpdateError(
            "Alembic head sau update không đúng: {0}".format(after["alembic_versions"])
        )
    before_counts = database_before.get("row_counts", {})
    for table, expected_count in before_counts.items():
        actual_count = after["row_counts"].get(table)
        if actual_count != expected_count:
            raise UpdateError(
                "Row count bị thay đổi ở {0}: trước={1}, sau={2}".format(
                    table, expected_count, actual_count
                )
            )
    return after


def _backup_file_path(backup_directory, relative):
    relative = normalized_relative_path(relative, allow_database=True)
    candidate = Path(backup_directory).joinpath(*PurePosixPath(relative).parts)
    root = Path(backup_directory).resolve()
    if candidate.is_symlink() or not candidate.is_file():
        raise UpdateError("Backup thiếu file thường: {0}".format(relative))
    if not _is_within(candidate.resolve(), root):
        raise UpdateError("Backup file thoát khỏi backup folder")
    return candidate


def restore_database(target, backup_directory, database_record):
    backup_file = _backup_file_path(backup_directory, database_record["backup_file"])
    expected_hash = database_record.get("sha256")
    if sha256_file(backup_file) != expected_hash:
        raise UpdateError("Checksum database backup không đúng; từ chối restore")
    backup_observations = observe_database(backup_file)
    if backup_observations["row_counts"] != database_record.get("row_counts", {}):
        raise UpdateError("Row counts trong database backup không khớp manifest")
    if backup_observations["alembic_versions"] != database_record.get("alembic_versions", []):
        raise UpdateError("Alembic version trong database backup không khớp manifest")

    relative_database = database_record.get("path", DEFAULT_DATABASE_PATH)
    if relative_database != DEFAULT_DATABASE_PATH:
        raise UpdateError("Backup manifest trỏ tới database path không được hỗ trợ")
    database_path = safe_target_path(target, relative_database, allow_database=True)
    temporary = database_path.with_name(
        ".{0}.{1}.restore-tmp".format(database_path.name, os.getpid())
    )
    shutil.copyfile(str(backup_file), str(temporary))
    mode = parse_mode(database_record.get("mode", "0644"))
    os.chmod(temporary, mode)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database_path) + suffix)
        if sidecar.exists():
            if sidecar.is_symlink() or not sidecar.is_file():
                temporary.unlink(missing_ok=True)
                raise UpdateError("SQLite sidecar không an toàn: {0}".format(sidecar))
            sidecar.unlink()
    os.replace(str(temporary), str(database_path))
    _fsync_directory(database_path.parent)

    if sha256_file(database_path) != expected_hash:
        raise UpdateError("Database restore không khớp checksum")
    restored = observe_database(database_path)
    if restored["row_counts"] != database_record.get("row_counts", {}):
        raise UpdateError("Database restore không giữ nguyên row counts")
    if restored["alembic_versions"] != database_record.get("alembic_versions", []):
        raise UpdateError("Database restore không giữ nguyên Alembic version")


def _remove_empty_new_parents(target, destination):
    target = Path(target).resolve()
    current = Path(destination).parent
    while current != target and _is_within(current.resolve(strict=False), target):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def restore_files(target, backup_directory, file_records):
    for record in reversed(file_records):
        relative = normalized_relative_path(record.get("path"))
        destination = safe_target_path(target, relative)
        if record.get("existed"):
            backup_relative = record.get("backup_file")
            if not backup_relative:
                raise UpdateError("File snapshot thiếu backup_file: {0}".format(relative))
            backup_file = _backup_file_path(backup_directory, backup_relative)
            if sha256_file(backup_file) != record.get("sha256"):
                raise UpdateError("Checksum file snapshot sai: {0}".format(relative))
            atomic_copy_file(
                backup_file,
                destination,
                parse_mode(record.get("mode", "0644")),
            )
            if sha256_file(destination) != record.get("sha256"):
                raise UpdateError("Không restore chính xác file: {0}".format(relative))
        else:
            if destination.exists() or destination.is_symlink():
                if destination.is_symlink() or not destination.is_file():
                    raise UpdateError("Không xóa target mới không phải file: {0}".format(relative))
                destination.unlink()
                _fsync_directory(destination.parent)
            _remove_empty_new_parents(target, destination)


def append_event(manifest, event, detail=None):
    item = {"at": utc_now(), "event": event}
    if detail:
        item["detail"] = str(detail)
    manifest.setdefault("events", []).append(item)


def write_backup_manifest(backup_directory, manifest):
    atomic_write_json(Path(backup_directory) / BACKUP_MANIFEST_NAME, manifest)


def restore_snapshot(target, backup_directory, snapshot_manifest):
    errors = []
    try:
        restore_database(target, backup_directory, snapshot_manifest["database"])
    except Exception as exc:  # continue so code restoration is still attempted
        errors.append("database: {0}".format(exc))
    try:
        restore_files(target, backup_directory, snapshot_manifest.get("files", []))
    except Exception as exc:
        errors.append("files: {0}".format(exc))
    if errors:
        raise UpdateError("; ".join(errors))


def install_update(target, manifest_path, payload_root):
    manifest = validate_payload_manifest(manifest_path, payload_root)
    target = validate_target(target)
    current_version = installed_version(target)
    allowed_versions = manifest.get("allowed_from_versions", ["0.2.76"])
    if current_version not in allowed_versions:
        raise UpdateError(
            "Bản hiện tại là {0}; package chỉ hỗ trợ {1}".format(
                current_version, ", ".join(allowed_versions)
            )
        )

    announce("Payload {0} đã qua kiểm tra checksum.".format(UPDATE_VERSION))
    stop_result = stop_application(target)
    backup_directory = create_unique_backup_directory(target, "update-0.2.77")
    announce("Đang tạo backup nhất quán trước update…")

    database_path = safe_target_path(target, DEFAULT_DATABASE_PATH, allow_database=True)
    database_record = create_database_backup(database_path, backup_directory / "afi_os.db")
    file_records = snapshot_target_files(
        target,
        backup_directory,
        [entry["path"] for entry in manifest["_entries"]],
    )
    backup_manifest = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "kind": "AFI_OS_UPDATE_BACKUP",
        "update_version": UPDATE_VERSION,
        "created_at": utc_now(),
        "target": str(target),
        "phase": "PREPARED",
        "installed_from_version": current_version,
        "expected_migration_head": expected_heads_from_manifest(manifest),
        "payload_manifest_sha256": manifest["_manifest_sha256"],
        "database": database_record,
        "files": file_records,
        "stop_result": stop_result,
        "events": [],
    }
    append_event(backup_manifest, "BACKUP_VERIFIED")
    write_backup_manifest(backup_directory, backup_manifest)
    announce("Backup đã xác minh: {0}".format(backup_directory.name))

    mutation_started = False
    try:
        mutation_started = True
        backup_manifest["phase"] = "APPLYING"
        append_event(backup_manifest, "PAYLOAD_COPY_STARTED")
        write_backup_manifest(backup_directory, backup_manifest)
        copy_payload(target, manifest["_entries"])
        append_event(backup_manifest, "PAYLOAD_COPY_COMPLETE")
        write_backup_manifest(backup_directory, backup_manifest)

        announce("Đang chạy migration 0.2.77…")
        migration = run_alembic_upgrade(
            target,
            database_path,
            backup_directory / "alembic-upgrade.log",
        )
        append_event(backup_manifest, "MIGRATION_COMPLETE")

        announce("Đang kiểm tra database và dữ liệu cũ…")
        after = verify_updated_database(
            database_path,
            database_record,
            expected_heads_from_manifest(manifest),
        )
        backup_manifest["migration"] = migration
        backup_manifest["post_update_database"] = after
        backup_manifest["phase"] = "INSTALLED"
        append_event(backup_manifest, "POST_UPDATE_VERIFIED")
        write_backup_manifest(backup_directory, backup_manifest)
    except BaseException as exc:
        if mutation_started:
            announce("Update lỗi; đang tự khôi phục database và code 0.2.76…")
            append_event(backup_manifest, "INSTALL_FAILED", exc)
            try:
                restore_snapshot(target, backup_directory, backup_manifest)
                backup_manifest["launchd_restore"] = restore_launchd_services(
                    target, stop_result.get("launchd_labels", [])
                )
                backup_manifest["phase"] = "AUTO_ROLLED_BACK"
                append_event(backup_manifest, "AUTO_ROLLBACK_VERIFIED")
            except Exception as rollback_exc:
                backup_manifest["phase"] = "ROLLBACK_FAILED"
                append_event(backup_manifest, "AUTO_ROLLBACK_FAILED", rollback_exc)
                write_backup_manifest(backup_directory, backup_manifest)
                raise UpdateError(
                    "Update thất bại ({0}); rollback cũng thất bại ({1}). "
                    "Không khởi động app và giữ nguyên backup {2}".format(
                        exc, rollback_exc, backup_directory
                    )
                )
            write_backup_manifest(backup_directory, backup_manifest)
        if isinstance(exc, KeyboardInterrupt):
            raise UpdateError("Update bị hủy; dữ liệu và code cũ đã được khôi phục")
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("Update thất bại: {0}".format(exc))

    try:
        backup_manifest["launchd_restore"] = restore_launchd_services(
            target, stop_result.get("launchd_labels", [])
        )
        append_event(backup_manifest, "PREVIOUS_SERVICES_RESTORED")
    except Exception as exc:
        backup_manifest["phase"] = "INSTALLED_SERVICE_STOPPED"
        append_event(backup_manifest, "SERVICE_RESTART_FAILED", exc)
        write_backup_manifest(backup_directory, backup_manifest)
        announce(
            "Cập nhật đã an toàn nhưng dịch vụ 24/7 chưa khởi động lại: {0}".format(exc)
        )
    else:
        write_backup_manifest(backup_directory, backup_manifest)

    announce("Cập nhật AFI-OS 0.2.77 thành công; dữ liệu cũ đã được giữ nguyên.")
    announce("Rollback point: {0}".format(backup_directory))
    return backup_directory


def load_update_backup(backup_directory):
    backup_directory = Path(backup_directory)
    manifest_path = backup_directory / BACKUP_MANIFEST_NAME
    manifest = load_json(manifest_path, "update backup manifest")
    if manifest.get("kind") != "AFI_OS_UPDATE_BACKUP":
        raise UpdateError("Backup không phải update backup AFI-OS")
    if manifest.get("update_version") != UPDATE_VERSION:
        raise UpdateError("Backup không thuộc bản 0.2.77")
    if not isinstance(manifest.get("database"), dict):
        raise UpdateError("Backup manifest thiếu database")
    if not isinstance(manifest.get("files"), list):
        raise UpdateError("Backup manifest thiếu file snapshots")
    return manifest


def latest_installed_backup(target):
    backup_root = safe_target_path(target, "backups", allow_database=True)
    candidates = []
    if backup_root.is_dir() and not backup_root.is_symlink():
        for path in backup_root.glob("update-0.2.77-*"):
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                manifest = load_update_backup(path)
            except UpdateError:
                continue
            if manifest.get("phase") in (
                "INSTALLED",
                "INSTALLED_SERVICE_STOPPED",
                "ROLLBACK_FAILED",
            ):
                candidates.append((manifest.get("created_at", ""), path, manifest))
    if not candidates:
        raise UpdateError("Không tìm thấy update-0.2.77 backup đang ở trạng thái INSTALLED")
    candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    return candidates[0][1], candidates[0][2]


def snapshot_current_state_for_emergency(target, source_manifest):
    emergency = create_unique_backup_directory(target, "emergency-before-rollback-0.2.77")
    database_path = safe_target_path(target, DEFAULT_DATABASE_PATH, allow_database=True)
    database_record = create_database_backup(database_path, emergency / "afi_os.db")
    file_records = snapshot_target_files(
        target,
        emergency,
        [record["path"] for record in source_manifest.get("files", [])],
    )
    manifest = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "kind": "AFI_OS_EMERGENCY_ROLLBACK_BACKUP",
        "update_version": UPDATE_VERSION,
        "created_at": utc_now(),
        "target": str(target),
        "phase": "VERIFIED",
        "database": database_record,
        "files": file_records,
        "events": [{"at": utc_now(), "event": "EMERGENCY_BACKUP_VERIFIED"}],
    }
    write_backup_manifest(emergency, manifest)
    return emergency, manifest


def rollback_update(target, backup_directory=None):
    target = validate_target(target)
    if backup_directory:
        backup_directory = Path(backup_directory).expanduser().resolve()
        backup_root = safe_target_path(target, "backups", allow_database=True).resolve()
        if not _is_within(backup_directory, backup_root):
            raise UpdateError("Rollback backup phải nằm trong target/backups")
        source_manifest = load_update_backup(backup_directory)
        if source_manifest.get("phase") not in (
            "INSTALLED",
            "INSTALLED_SERVICE_STOPPED",
            "ROLLBACK_FAILED",
        ):
            raise UpdateError("Update backup không ở trạng thái có thể rollback")
    else:
        backup_directory, source_manifest = latest_installed_backup(target)

    stop_result = stop_application(target)
    announce("Đang tạo emergency backup của trạng thái 0.2.77 hiện tại…")
    emergency_directory, emergency_manifest = snapshot_current_state_for_emergency(
        target, source_manifest
    )
    announce("Emergency backup đã xác minh: {0}".format(emergency_directory.name))

    try:
        announce("Đang khôi phục database và code trước update 0.2.77…")
        restore_snapshot(target, backup_directory, source_manifest)
        source_manifest["launchd_restore"] = restore_launchd_services(
            target, stop_result.get("launchd_labels", [])
        )
        source_manifest["phase"] = "ROLLED_BACK"
        source_manifest["rollback_at"] = utc_now()
        source_manifest["emergency_backup"] = emergency_directory.name
        append_event(source_manifest, "MANUAL_ROLLBACK_VERIFIED")
        write_backup_manifest(backup_directory, source_manifest)
    except BaseException as exc:
        announce("Rollback lỗi; đang khôi phục lại trạng thái 0.2.77 từ emergency backup…")
        try:
            restore_snapshot(target, emergency_directory, emergency_manifest)
            restore_launchd_services(target, stop_result.get("launchd_labels", []))
            source_manifest["phase"] = "INSTALLED"
            append_event(source_manifest, "MANUAL_ROLLBACK_FAILED_AND_RECOVERED", exc)
            write_backup_manifest(backup_directory, source_manifest)
        except Exception as emergency_exc:
            source_manifest["phase"] = "ROLLBACK_FAILED"
            append_event(source_manifest, "EMERGENCY_RECOVERY_FAILED", emergency_exc)
            write_backup_manifest(backup_directory, source_manifest)
            raise UpdateError(
                "Rollback thất bại ({0}); emergency recovery cũng thất bại ({1}). "
                "Không khởi động app.".format(exc, emergency_exc)
            )
        if isinstance(exc, KeyboardInterrupt):
            raise UpdateError("Rollback bị hủy; trạng thái 0.2.77 đã được phục hồi")
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("Rollback thất bại: {0}".format(exc))

    announce("Rollback 0.2.77 thành công.")
    announce("Bản emergency trước rollback nằm tại: {0}".format(emergency_directory))
    return backup_directory


def default_target():
    return os.environ.get("AFI_OS_TARGET", str(Path.home() / "Downloads" / "AFI-OS"))


def default_package_paths():
    package_root = Path(__file__).resolve().parent
    return package_root / "payload-manifest.json", package_root / "payload"


def build_parser():
    manifest_default, payload_default = default_package_paths()
    parser = argparse.ArgumentParser(description="AFI-OS 0.2.77 safe updater")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="Install AFI-OS 0.2.77")
    install_parser.add_argument("--target", default=default_target())
    install_parser.add_argument("--manifest", default=str(manifest_default))
    install_parser.add_argument("--payload", default=str(payload_default))

    verify_parser = subparsers.add_parser("verify-package", help="Verify release payload")
    verify_parser.add_argument("--manifest", default=str(manifest_default))
    verify_parser.add_argument("--payload", default=str(payload_default))

    rollback_parser = subparsers.add_parser("rollback", help="Rollback latest AFI-OS 0.2.77")
    rollback_parser.add_argument("--target", default=default_target())
    rollback_parser.add_argument("--backup", default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-package":
            manifest = validate_payload_manifest(args.manifest, args.payload)
            announce("Payload hợp lệ: {0} files".format(len(manifest["_entries"])))
            return 0
        if args.command == "install":
            install_update(args.target, args.manifest, args.payload)
            return 0
        if args.command == "rollback":
            rollback_update(args.target, args.backup)
            return 0
        parser.error("Unknown command")
    except UpdateError as exc:
        print("[AFI-OS] LỖI: {0}".format(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
