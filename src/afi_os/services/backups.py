from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from afi_os import __version__
from afi_os.config import get_settings


def database_path() -> Path:
    settings = get_settings()
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise RuntimeError("Backup 0.2.0 chỉ hỗ trợ SQLite local-first")
    raw = settings.database_url[len(prefix):]
    path = Path(raw)
    if not path.is_absolute():
        path = settings.project_root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def backup_root() -> Path:
    root = get_settings().project_root / "backups"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_backup_folder(prefix: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    folder = backup_root() / f"{prefix}-{stamp}"
    suffix = 1
    while folder.exists():
        folder = backup_root() / f"{prefix}-{stamp}-{suffix}"
        suffix += 1
    folder.mkdir(mode=0o700)
    return folder


def _read_json_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _database_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("File backup không tồn tại hoặc không an toàn")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _alembic_versions(connection: sqlite3.Connection) -> list[str]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
    ).fetchone()
    if not exists:
        return []
    return sorted(
        str(row[0])
        for row in connection.execute("SELECT version_num FROM alembic_version")
    )


def _inspect_database(path: Path) -> dict:
    with _database_connection(path) as connection:
        integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
        foreign_key_rows = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        versions = _alembic_versions(connection)
    return {
        "integrity_check": "ok" if integrity_rows == ["ok"] else "; ".join(integrity_rows),
        "foreign_key_check": "ok" if not foreign_key_rows else foreign_key_rows,
        "alembic_versions": versions,
    }


def expected_schema_heads() -> list[str]:
    versions_root = get_settings().project_root / "migrations" / "versions"
    if not versions_root.is_dir() or versions_root.is_symlink():
        return []
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in versions_root.glob("*.py"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError):
            continue
        values: dict[str, object] = {}
        for statement in tree.body:
            name = None
            value_node = None
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                name = statement.target.id
                value_node = statement.value
            elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    name = target.id
                    value_node = statement.value
            if name not in {"revision", "down_revision"} or value_node is None:
                continue
            try:
                values[name] = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                continue
        revision = values.get("revision")
        if isinstance(revision, str) and revision:
            revisions.add(revision)
        down_revision = values.get("down_revision")
        if isinstance(down_revision, str) and down_revision:
            parents.add(down_revision)
        elif isinstance(down_revision, (list, tuple)):
            parents.update(item for item in down_revision if isinstance(item, str) and item)
    return sorted(revisions - parents)


def _safe_created_at(raw: object, db_file: Path) -> str:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(db_file.stat().st_mtime, UTC).isoformat()


def _manifest_for(folder: Path) -> dict:
    db_file = folder / "afi_os.db"
    manifest = _read_json_object(folder / "manifest.json")
    update_manifest = _read_json_object(folder / "update-manifest.json") if not manifest else {}
    update_database = update_manifest.get("database", {})
    if not isinstance(update_database, dict):
        update_database = {}

    declared_sha = manifest.get("sha256") or update_database.get("sha256")
    declared_heads = manifest.get("alembic_versions") or update_database.get("alembic_versions")
    code_heads = expected_schema_heads()
    actual_sha = sha256_file(db_file)
    inspection = None
    try:
        inspection = _inspect_database(db_file)
        actual_heads = inspection["alembic_versions"]
    except (OSError, RuntimeError, sqlite3.DatabaseError):
        actual_heads = []
        database_status = "INVALID"
    else:
        declared_sha_is_valid = bool(
            isinstance(declared_sha, str)
            and len(declared_sha) == 64
            and all(character in "0123456789abcdefABCDEF" for character in declared_sha)
        )
        if declared_sha is not None and (
            not declared_sha_is_valid
            or not hmac.compare_digest(actual_sha.lower(), declared_sha.lower())
        ):
            database_status = "CHECKSUM_MISMATCH"
        elif inspection["integrity_check"] != "ok":
            database_status = "INTEGRITY_ERROR"
        elif inspection["foreign_key_check"] != "ok":
            database_status = "FOREIGN_KEY_ERROR"
        elif (
            declared_heads is not None
            and (
                not isinstance(declared_heads, list)
                or sorted(str(head) for head in declared_heads) != actual_heads
            )
        ):
            database_status = "SCHEMA_MISMATCH"
        elif not code_heads or not actual_heads or actual_heads != code_heads:
            database_status = "SCHEMA_MISMATCH"
        else:
            database_status = "OK"

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        update_version = update_manifest.get("update_version")
        version = f"pre-update-{update_version}" if update_version else "unknown"

    return {
        "name": folder.name,
        "created_at": _safe_created_at(
            manifest.get("created_at") or update_manifest.get("created_at"), db_file
        ),
        "size_bytes": db_file.stat().st_size,
        "sha256": actual_sha,
        "database_file": str(db_file),
        "version": version,
        "alembic_versions": actual_heads,
        "declared_alembic_versions": declared_heads if isinstance(declared_heads, list) else [],
        "expected_sha256": declared_sha if isinstance(declared_sha, str) else None,
        "database_status": database_status,
    }


def backup_is_verified(item: dict) -> bool:
    return item.get("database_status") == "OK"


def create_backup(prefix: str = "manual") -> dict:
    source_path = database_path()
    if not source_path.is_file() or source_path.is_symlink() or source_path.stat().st_size == 0:
        raise RuntimeError("Backup thất bại: database nguồn không tồn tại hoặc không an toàn")

    code_heads = expected_schema_heads()
    if not code_heads:
        raise RuntimeError("Backup thất bại: không xác định được schema hiện tại từ migration")

    try:
        source_inspection = _inspect_database(source_path)
    except (OSError, RuntimeError, sqlite3.DatabaseError) as exc:
        raise RuntimeError(f"Backup thất bại: không kiểm tra được database nguồn: {exc}") from exc
    if source_inspection["integrity_check"] != "ok":
        raise RuntimeError(
            f"Backup thất bại: database nguồn lỗi integrity: "
            f"{source_inspection['integrity_check']}"
        )
    if source_inspection["foreign_key_check"] != "ok":
        raise RuntimeError("Backup thất bại: database nguồn có lỗi foreign key")
    if source_inspection["alembic_versions"] != code_heads:
        raise RuntimeError(
            "Backup thất bại: schema database nguồn không trùng migration hiện tại "
            f"({source_inspection['alembic_versions']} != {code_heads})"
        )

    folder: Path | None = None
    try:
        folder = _unique_backup_folder(prefix)
        destination = folder / "afi_os.db"
        with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
            checkpoint = source.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            if checkpoint is not None and int(checkpoint[0]) != 0:
                raise RuntimeError("database WAL đang bận; chưa tạo backup")
            source.backup(target)

        inspection = _inspect_database(destination)
        if inspection["integrity_check"] != "ok":
            raise RuntimeError(f"backup lỗi integrity: {inspection['integrity_check']}")
        if inspection["foreign_key_check"] != "ok":
            raise RuntimeError("backup có lỗi foreign key")
        if inspection["alembic_versions"] != code_heads:
            raise RuntimeError(
                "schema bản sao không trùng migration hiện tại "
                f"({inspection['alembic_versions']} != {code_heads})"
            )

        checksum = sha256_file(destination)
        manifest = {
            "name": folder.name,
            "created_at": datetime.now(UTC).isoformat(),
            "size_bytes": destination.stat().st_size,
            "sha256": checksum,
            "database_file": str(destination),
            "version": __version__,
            "alembic_versions": inspection["alembic_versions"],
            "integrity_check": inspection["integrity_check"],
            "foreign_key_check": inspection["foreign_key_check"],
            "source_alembic_versions": source_inspection["alembic_versions"],
            "database_status": "OK",
        }
        manifest_path = folder / "manifest.json"
        temporary_manifest = folder / "manifest.json.tmp"
        temporary_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_manifest.replace(manifest_path)

        verified = _manifest_for(folder)
        if verified["database_status"] != "OK" or not hmac.compare_digest(
            str(verified["sha256"]).lower(), checksum.lower()
        ):
            raise RuntimeError(
                f"hậu kiểm backup không đạt: {verified['database_status']}"
            )
        return manifest
    except Exception as exc:
        if folder is not None and folder.is_dir() and folder.parent == backup_root():
            shutil.rmtree(folder)
        if isinstance(exc, RuntimeError) and str(exc).startswith("Backup thất bại:"):
            raise
        raise RuntimeError(f"Backup thất bại: {exc}") from exc


def _create_raw_emergency_backup(source: Path, schema_heads: list[str]) -> dict:
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("Database hiện tại không phải file thường; chưa thể giữ bản khẩn cấp")
    folder = _unique_backup_folder("emergency-before-restore-raw")
    destination = folder / "afi_os.db"
    shutil.copy2(source, destination)
    copied_files = []
    for source_file in (source, Path(f"{source}-wal"), Path(f"{source}-shm")):
        if source_file == source:
            copied = destination
        elif source_file.is_file() and not source_file.is_symlink():
            copied = folder / f"{source_file.name}.preserved"
            shutil.copy2(source_file, copied)
        else:
            continue
        copied_files.append(
            {
                "name": copied.name,
                "size_bytes": copied.stat().st_size,
                "sha256": sha256_file(copied),
            }
        )
    manifest = {
        "name": folder.name,
        "kind": "AFI_OS_EMERGENCY_RAW_SNAPSHOT",
        "created_at": datetime.now(UTC).isoformat(),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "database_file": str(destination),
        "version": __version__,
        "alembic_versions": schema_heads,
        "integrity_check": "not-run-raw-snapshot",
        "foreign_key_check": "not-run-raw-snapshot",
        "source_status": "NOT_OPENED_TO_PRESERVE_EXACT_BYTES",
        "copied_files": copied_files,
    }
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def list_backups() -> list[dict]:
    items = []
    for folder in backup_root().iterdir():
        db_file = folder / "afi_os.db"
        if (
            folder.is_dir()
            and not folder.is_symlink()
            and db_file.is_file()
            and not db_file.is_symlink()
        ):
            try:
                items.append(_manifest_for(folder))
            except (OSError, sqlite3.DatabaseError):
                continue
    return sorted(items, key=lambda item: item["created_at"], reverse=True)


def restore_latest() -> dict:
    all_candidates = [
        item
        for item in list_backups()
        if not item["name"].startswith("emergency-")
    ]
    if not all_candidates:
        raise RuntimeError("Không có backup nào để khôi phục")
    candidates = [item for item in all_candidates if backup_is_verified(item)]
    if not candidates:
        raise RuntimeError("Không có backup toàn vẹn tương thích với schema hiện tại")

    target = database_path()
    code_heads = expected_schema_heads()
    target_inspection = None
    if target.exists() and not code_heads:
        try:
            target_inspection = _inspect_database(target)
        except (OSError, RuntimeError, sqlite3.DatabaseError):
            target_inspection = None

    target_heads = code_heads or (
        target_inspection["alembic_versions"] if target_inspection is not None else []
    )
    if not target_heads:
        raise RuntimeError("Không xác định được schema hiện tại từ code hoặc database")

    selected = None
    selected_inspection = None
    for candidate in candidates:
        source = backup_root() / candidate["name"] / "afi_os.db"
        expected_sha = candidate.get("expected_sha256")
        if expected_sha and (
            len(expected_sha) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in expected_sha)
            or not hmac.compare_digest(candidate["sha256"].lower(), expected_sha.lower())
        ):
            continue
        try:
            inspection = _inspect_database(source)
        except (OSError, RuntimeError, sqlite3.DatabaseError):
            continue
        if inspection["integrity_check"] != "ok" or inspection["foreign_key_check"] != "ok":
            continue
        declared_heads = candidate.get("declared_alembic_versions")
        if declared_heads and sorted(str(head) for head in declared_heads) != inspection[
            "alembic_versions"
        ]:
            continue
        if inspection["alembic_versions"] != target_heads:
            continue
        selected = candidate
        selected_inspection = inspection
        break

    if selected is None or selected_inspection is None:
        raise RuntimeError("Không có backup toàn vẹn tương thích với schema hiện tại")

    source = backup_root() / selected["name"] / "afi_os.db"
    emergency = None
    if target.exists():
        emergency = _create_raw_emergency_backup(target, target_heads)
    temp = target.with_suffix(".restore.tmp")
    try:
        temp.unlink(missing_ok=True)
        shutil.copy2(source, temp)
        temp_inspection = _inspect_database(temp)
        if temp_inspection["integrity_check"] != "ok":
            raise RuntimeError(f"Backup không hợp lệ: {temp_inspection['integrity_check']}")
        if temp_inspection["foreign_key_check"] != "ok":
            raise RuntimeError("Backup có lỗi foreign key")
        if temp_inspection["alembic_versions"] != selected_inspection["alembic_versions"]:
            raise RuntimeError("Schema backup thay đổi trong lúc khôi phục")
        temp.replace(target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    return {"restored": selected, "emergency_backup": emergency}
