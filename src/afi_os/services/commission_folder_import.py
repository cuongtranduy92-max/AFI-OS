from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from afi_os.enums import SyncStatus
from afi_os.models import Program, SyncRun
from afi_os.services.commission_import import (
    analyze_import,
    commit_import,
    decode_csv,
    detect_delimiter,
    normalize_key,
)

CONNECTOR = "AFFILIATE_COMMISSION_FOLDER"
MAX_REPORT_BYTES = 10 * 1024 * 1024
CACHE_VERSION = 2
PROGRAM_COLUMN_ALIASES = {
    "program_domain",
    "merchant_domain",
    "website_domain",
    "merchant",
    "advertiser",
    "program",
}


def _family(path: Path) -> str | None:
    normalized = re.sub(r"_\d+$", "", normalize_key(path.stem))
    if re.search(r"(^|_)(commissions?|hoa_hong)(_|$)", normalized):
        return normalized
    return None


def discover_commission_reports(
    root: Path | None = None,
    *,
    now: datetime | None = None,
    min_age_seconds: int = 60,
) -> list[Path]:
    root = (root or Path.home() / "Downloads").expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        return []
    now = now or datetime.now(UTC)
    newest_by_family: dict[str, Path] = {}
    for path in root.iterdir():
        if path.suffix.lower() != ".csv" or path.is_symlink() or not path.is_file():
            continue
        family = _family(path)
        if family is None:
            continue
        stat = path.stat()
        if stat.st_size <= 0 or stat.st_size > MAX_REPORT_BYTES:
            continue
        if now.timestamp() - stat.st_mtime < min_age_seconds:
            continue
        previous = newest_by_family.get(family)
        if previous is None or (stat.st_mtime_ns, path.name) > (
            previous.stat().st_mtime_ns,
            previous.name,
        ):
            newest_by_family[family] = path
    return sorted(newest_by_family.values(), key=lambda path: path.name)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_key(digest: str, family: str) -> str:
    return f"{digest}:{family}"


def _previous_results(db: Session) -> dict[str, dict]:
    latest = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    if latest is None or latest.metadata_json.get("cache_version") != CACHE_VERSION:
        return {}
    return {
        item["cache_key"]: item
        for item in latest.metadata_json.get("file_results", [])
        if isinstance(item, dict) and isinstance(item.get("cache_key"), str)
    }


def _program_markers(program: Program) -> set[str]:
    domain = normalize_key(program.merchant.website_domain)
    root = normalize_key(program.merchant.website_domain.split(".", 1)[0])
    merchant = normalize_key(program.merchant.name)
    program_name = normalize_key(program.name)
    reduced_name = re.sub(
        r"(^|_)(affiliate|partner|program|programme)(_|$)",
        "_",
        program_name,
    ).strip("_")
    return {
        marker
        for marker in {domain, root, merchant, reduced_name}
        if len(marker) >= 4
    }


def _contains_marker(value: str, marker: str) -> bool:
    return bool(re.search(rf"(^|_){re.escape(marker)}(_|$)", value))


def _embedded_program_values(data: bytes) -> set[str]:
    text = decode_csv(data)
    reader = csv.DictReader(io.StringIO(text), delimiter=detect_delimiter(text))
    if not reader.fieldnames:
        return set()
    columns = {
        name
        for name in reader.fieldnames
        if name and normalize_key(name) in PROGRAM_COLUMN_ALIASES
    }
    if not columns:
        return set()
    values: set[str] = set()
    for index, row in enumerate(reader):
        if index >= 2000:
            break
        for column in columns:
            normalized = normalize_key(row.get(column, ""))
            if normalized:
                values.add(normalized)
    return values


def match_report_program(
    programs: list[Program],
    *,
    path: Path,
    data: bytes,
) -> Program | None:
    filename = normalize_key(path.stem)
    embedded = _embedded_program_values(data)
    matches: list[Program] = []
    for program in programs:
        markers = _program_markers(program)
        filename_match = any(_contains_marker(filename, marker) for marker in markers)
        embedded_match = any(
            any(_contains_marker(value, marker) for marker in markers)
            for value in embedded
        )
        if filename_match or embedded_match:
            matches.append(program)
    return matches[0] if len(matches) == 1 else None


def _source_for(program: Program) -> str:
    return f"AFFILIATE_{normalize_key(program.merchant.website_domain).upper()}"


def import_downloaded_commission_reports(
    db: Session,
    *,
    root: Path | None = None,
    now: datetime | None = None,
    min_age_seconds: int = 60,
) -> dict:
    now = now or datetime.now(UTC)
    candidates = discover_commission_reports(
        root,
        now=now,
        min_age_seconds=min_age_seconds,
    )
    previous_by_key = _previous_results(db)
    programs = list(
        db.scalars(
            select(Program)
            .options(selectinload(Program.merchant))
            .order_by(Program.id.asc())
        ).all()
    )

    file_results: list[dict] = []
    rows_read = 0
    rows_written = 0
    processed = 0
    unchanged = 0
    retried_after_error = 0
    retried_after_mapping = 0
    error_count = 0
    mapping_required_count = 0

    for path in candidates:
        digest = ""
        family = _family(path) or normalize_key(path.stem)
        cache_key = ""
        previous_status = None
        try:
            data = path.read_bytes()
            digest = _sha256(data)
            cache_key = _cache_key(digest, family)
            previous = previous_by_key.get(cache_key)
            previous_status = previous.get("status") if previous is not None else None
            retryable_previous = previous_status in {"ERROR", "MAPPING_REQUIRED"}
            if previous is not None and not retryable_previous:
                carried = dict(previous)
                carried.update(
                    {
                        "filename": path.name,
                        "checked_at": now.isoformat(),
                        "unchanged": True,
                    }
                )
                file_results.append(carried)
                unchanged += 1
                error_count += int(carried.get("status") == "ERROR")
                mapping_required_count += int(
                    carried.get("status") == "MAPPING_REQUIRED"
                )
                continue
            if previous_status == "ERROR":
                retried_after_error += 1
            elif previous_status == "MAPPING_REQUIRED":
                retried_after_mapping += 1

            processed += 1
            program = match_report_program(programs, path=path, data=data)
            if program is None:
                mapping_required_count += 1
                file_results.append(
                    {
                        "filename": path.name,
                        "family": family,
                        "sha256": digest,
                        "cache_key": cache_key,
                        "status": "MAPPING_REQUIRED",
                        "checked_at": now.isoformat(),
                        "unchanged": False,
                        "retry_reason": previous_status,
                        "rows_read": 0,
                        "rows_written": 0,
                        "program_id": None,
                        "program_name": None,
                        "merchant_domain": None,
                        "source": None,
                        "error": (
                            "Không xác định duy nhất chương trình từ tên file hoặc cột "
                            "program_domain/merchant"
                        ),
                    }
                )
                continue

            source = _source_for(program)
            analysis = analyze_import(db, data, source)
            rows_read += analysis["rows_read"]
            if analysis["error_count"] or analysis["conflict_count"]:
                error_count += 1
                detail = (
                    analysis["errors"][0]["message"]
                    if analysis["errors"]
                    else f"Báo cáo có {analysis['conflict_count']} xung đột"
                )
                file_results.append(
                    {
                        "filename": path.name,
                        "family": family,
                        "sha256": digest,
                        "cache_key": cache_key,
                        "status": "ERROR",
                        "checked_at": now.isoformat(),
                        "unchanged": False,
                        "retry_reason": previous_status,
                        "rows_read": analysis["rows_read"],
                        "rows_written": 0,
                        "program_id": program.id,
                        "program_name": program.name,
                        "merchant_domain": program.merchant.website_domain,
                        "source": source,
                        "error": detail,
                    }
                )
                continue

            written = (
                commit_import(db, analysis, program_id=program.id)
                if analysis["valid_rows"]
                else 0
            )
            rows_written += written
            file_results.append(
                {
                    "filename": path.name,
                    "family": family,
                    "sha256": digest,
                    "cache_key": cache_key,
                    "status": "IMPORTED" if written else "UP_TO_DATE",
                    "checked_at": now.isoformat(),
                    "unchanged": False,
                    "retry_reason": previous_status,
                    "rows_read": analysis["rows_read"],
                    "rows_written": written,
                    "program_id": program.id,
                    "program_name": program.name,
                    "merchant_domain": program.merchant.website_domain,
                    "source": source,
                    "error": None,
                }
            )
        except (OSError, SQLAlchemyError, ValueError) as exc:
            db.rollback()
            error_count += 1
            processed += int(not cache_key)
            file_results.append(
                {
                    "filename": path.name,
                    "family": family,
                    "sha256": digest,
                    "cache_key": cache_key or _cache_key(digest, family),
                    "status": "ERROR",
                    "checked_at": now.isoformat(),
                    "unchanged": False,
                    "retry_reason": previous_status,
                    "rows_read": 0,
                    "rows_written": 0,
                    "program_id": None,
                    "program_name": None,
                    "merchant_domain": None,
                    "source": None,
                    "error": str(exc),
                }
            )

    status = (
        SyncStatus.PARTIAL
        if error_count or mapping_required_count
        else SyncStatus.SUCCESS
    )
    report = {
        "status": status.value,
        "cache_version": CACHE_VERSION,
        "input_folder": "~/Downloads",
        "files_seen": len(candidates),
        "files_processed": processed,
        "files_unchanged": unchanged,
        "files_retried_after_error": retried_after_error,
        "files_retried_after_mapping": retried_after_mapping,
        "rows_read": rows_read,
        "rows_written": rows_written,
        "error_count": error_count,
        "mapping_required_count": mapping_required_count,
        "file_results": file_results,
    }
    db.add(
        SyncRun(
            connector=CONNECTOR,
            started_at=now,
            ended_at=datetime.now(UTC),
            status=status,
            rows_read=rows_read,
            rows_written=rows_written,
            error_summary=(
                "; ".join(
                    f"{item['filename']}: {item['error']}"
                    for item in file_results
                    if item.get("status") in {"ERROR", "MAPPING_REQUIRED"}
                )
                or None
            ),
            metadata_json=report,
        )
    )
    db.commit()
    return report
