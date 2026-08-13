from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from afi_os.enums import SyncStatus
from afi_os.models import AdsAccount, SyncRun
from afi_os.services.campaign_import import (
    analyze_campaign_import,
    commit_campaign_import,
    inspect_campaign_report_signature,
)
from afi_os.services.commission_import import normalize_key

CONNECTOR = "GOOGLE_ADS_FOLDER"
MAX_REPORT_BYTES = 10 * 1024 * 1024
CONTENT_SNIFF_BYTES = 256 * 1024
CACHE_VERSION = 9
MAX_DATA_LAG = timedelta(days=1)
INTRADAY_REPORT_MAX_AGE = timedelta(hours=6)
CONFIRMED_STATUSES = {"IMPORTED", "UP_TO_DATE"}


@dataclass(frozen=True)
class CampaignReportDiscovery:
    reports: list[Path]
    rejected_candidates: list[dict]


def _family(path: Path) -> str | None:
    normalized = re.sub(r"_\d+$", "", normalize_key(path.stem))
    if normalized.startswith("bao_cao_chien_dich"):
        return "bao_cao_chien_dich"
    if normalized.startswith("campaign_report"):
        return "campaign_report"
    if normalized.startswith("google_ads_campaign"):
        return "google_ads_campaign"
    return None


def _discover_campaign_report_inputs(
    root: Path | None = None,
    *,
    now: datetime | None = None,
    min_age_seconds: int = 60,
) -> CampaignReportDiscovery:
    root = (root or Path.home() / "Downloads").expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        return CampaignReportDiscovery(reports=[], rejected_candidates=[])
    now = now or datetime.now(UTC)
    newest_by_family: dict[str, tuple[Path, int]] = {}
    near_matches: list[tuple[Path, int, float, dict]] = []
    for path in root.iterdir():
        if path.suffix.lower() != ".csv" or path.is_symlink() or not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0 or stat.st_size > MAX_REPORT_BYTES:
            continue
        age_seconds = now.timestamp() - stat.st_mtime
        if age_seconds < min_age_seconds:
            continue
        family = _family(path)
        if family is None:
            try:
                with path.open("rb") as handle:
                    prefix = handle.read(CONTENT_SNIFF_BYTES)
            except OSError:
                continue
            signature = inspect_campaign_report_signature(prefix)
            if signature["is_near_match"]:
                near_matches.append(
                    (path, stat.st_mtime_ns, stat.st_mtime, signature)
                )
            if not (
                signature["is_report"]
                or signature.get("is_campaign_id_recoverable")
            ):
                continue
            family = "content_signature"
        previous = newest_by_family.get(family)
        if previous is None or (stat.st_mtime_ns, path.name) > (
            previous[1],
            previous[0].name,
        ):
            newest_by_family[family] = (path, stat.st_mtime_ns)
    reports = sorted(
        (item[0] for item in newest_by_family.values()),
        key=lambda path: path.name,
    )
    newest_report_mtime_ns = max(
        (item[1] for item in newest_by_family.values()),
        default=-1,
    )
    rejected_candidates: list[dict] = []
    if near_matches:
        path, modified_ns, modified_at, signature = max(
            near_matches,
            key=lambda item: (item[1], item[0].name),
        )
        if modified_ns > newest_report_mtime_ns:
            rejected_candidates.append(
                {
                    "filename": path.name,
                    "status": "MISSING_REQUIRED_COLUMNS",
                    "missing_fields": signature["missing_fields"],
                    "missing_columns": signature["missing_columns"],
                    "modified_at": datetime.fromtimestamp(
                        modified_at,
                        UTC,
                    ).isoformat(),
                }
            )
    return CampaignReportDiscovery(
        reports=reports,
        rejected_candidates=rejected_candidates,
    )


def discover_campaign_reports(
    root: Path | None = None,
    *,
    now: datetime | None = None,
    min_age_seconds: int = 60,
) -> list[Path]:
    return _discover_campaign_report_inputs(
        root,
        now=now,
        min_age_seconds=min_age_seconds,
    ).reports


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized_customer_id(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 10 else (value or "").strip()


def _campaign_report_account_identity(
    analysis: dict,
    accounts: list[AdsAccount],
    *,
    has_customer_id_column: bool,
) -> dict:
    rows = analysis.get("_identity_rows", analysis.get("_rows", []))
    configured_by_id = {
        _normalized_customer_id(account.external_id): account for account in accounts
    }
    expected_customer_ids = sorted(account.external_id for account in accounts)
    reported_customer_ids = sorted(
        {row.account_external_id for row in rows if row.account_external_id}
    )
    reported_currencies = sorted(
        {
            row.currency
            for row in rows
            if "currency" in row.provided_fields and row.currency
        }
    )
    explicit_customer_id_rows = sum(row.account_id_explicit for row in rows)
    fallback_customer_id_rows = len(rows) - explicit_customer_id_rows
    explicit_currency_rows = sum(
        "currency" in row.provided_fields for row in rows
    )
    fallback_currency_rows = len(rows) - explicit_currency_rows
    result = {
        "allowed": True,
        "status": "NO_VALID_ROWS",
        "has_customer_id_column": has_customer_id_column,
        "expected_customer_ids": expected_customer_ids,
        "reported_customer_ids": reported_customer_ids,
        "reported_currencies": reported_currencies,
        "explicit_customer_id_rows": explicit_customer_id_rows,
        "fallback_customer_id_rows": fallback_customer_id_rows,
        "explicit_currency_rows": explicit_currency_rows,
        "fallback_currency_rows": fallback_currency_rows,
        "error": None,
    }
    if not rows:
        return result
    if not accounts:
        if fallback_currency_rows:
            result.update(
                {
                    "allowed": False,
                    "status": "ACCOUNT_CURRENCY_REQUIRED",
                    "error": (
                        "Chưa có tài khoản AFI-OS và báo cáo thiếu Currency code; "
                        "không thể tạo tài khoản an toàn"
                    ),
                }
            )
            return result
        result["status"] = (
            "VERIFIED_BOOTSTRAP_CUSTOMER_ID"
            if has_customer_id_column
            else "UNVERIFIED_BOOTSTRAP"
        )
        return result

    if has_customer_id_column:
        if fallback_customer_id_rows:
            result.update(
                {
                    "allowed": False,
                    "status": "CUSTOMER_ID_VALUE_REQUIRED",
                    "error": (
                        "Báo cáo có cột Customer ID nhưng có "
                        f"{fallback_customer_id_rows} dòng để trống; không thể coi "
                        "tài khoản là đã xác minh"
                    ),
                }
            )
            return result
        unknown_ids = sorted(
            {
                row.account_external_id
                for row in rows
                if _normalized_customer_id(row.account_external_id)
                not in configured_by_id
            }
        )
        if unknown_ids:
            result.update(
                {
                    "allowed": False,
                    "status": "CUSTOMER_ID_MISMATCH",
                    "error": (
                        "Báo cáo thuộc Customer ID "
                        f"{', '.join(unknown_ids)}, khác tài khoản AFI-OS "
                        f"{', '.join(expected_customer_ids)}"
                    ),
                }
            )
            return result
    elif len(accounts) != 1:
        result.update(
            {
                "allowed": False,
                "status": "CUSTOMER_ID_REQUIRED",
                "error": (
                    "Báo cáo thiếu Customer ID nên không thể xác định tài khoản "
                    "Google Ads an toàn"
                ),
            }
        )
        return result
    elif fallback_currency_rows:
        result.update(
            {
                "allowed": False,
                "status": "ACCOUNT_CURRENCY_REQUIRED",
                "error": (
                    "Báo cáo thiếu Customer ID nên Currency code phải có ở mọi "
                    f"dòng; hiện có {fallback_currency_rows} dòng để trống"
                ),
            }
        )
        return result

    currency_mismatches: list[str] = []
    for row in rows:
        if "currency" not in row.provided_fields:
            continue
        account = configured_by_id.get(_normalized_customer_id(row.account_external_id))
        if account is None:
            continue
        expected_currency = (account.currency or "").strip().upper()
        if expected_currency and row.currency != expected_currency:
            currency_mismatches.append(
                f"{row.account_external_id}: {row.currency} ≠ {expected_currency}"
            )
    if currency_mismatches:
        result.update(
            {
                "allowed": False,
                "status": "ACCOUNT_CURRENCY_MISMATCH",
                "error": (
                    "Tiền tệ báo cáo không khớp tài khoản Google Ads: "
                    + "; ".join(sorted(set(currency_mismatches)))
                ),
            }
        )
        return result

    result["status"] = (
        "VERIFIED_CUSTOMER_ID"
        if has_customer_id_column
        else "INFERRED_SINGLE_ACCOUNT_CURRENCY"
    )
    return result


def latest_metric_date(file_results: list[dict]) -> date | None:
    values: list[date] = []
    for item in file_results:
        if not isinstance(item, dict) or item.get("status") == "ERROR":
            continue
        try:
            values.append(date.fromisoformat(str(item.get("metric_date_to"))))
        except ValueError:
            continue
    return max(values, default=None)


def ads_report_is_stale(file_results: list[dict], *, today: date) -> bool:
    latest = latest_metric_date(file_results)
    return latest is not None and latest < today - MAX_DATA_LAG


def latest_report_source_at(file_results: list[dict]) -> datetime | None:
    """Return the newest source timestamp covering the latest metric date."""
    latest = latest_metric_date(file_results)
    if latest is None:
        return None
    values: list[datetime] = []
    for item in file_results:
        if not isinstance(item, dict) or item.get("status") == "ERROR":
            continue
        try:
            metric_date_to = date.fromisoformat(str(item.get("metric_date_to")))
        except ValueError:
            continue
        if metric_date_to != latest:
            continue
        source_modified_at = _result_modified_at(item)
        if source_modified_at is not None:
            values.append(source_modified_at)
    return max(values, default=None)


def ads_report_intraday_refresh_due(
    file_results: list[dict],
    *,
    now: datetime,
) -> bool:
    """Flag a same-day CSV whose source snapshot is more than six hours old."""
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    latest = latest_metric_date(file_results)
    source_modified_at = latest_report_source_at(file_results)
    return bool(
        latest == now.date()
        and source_modified_at is not None
        and now >= source_modified_at + INTRADAY_REPORT_MAX_AGE
    )


def _result_family(item: dict) -> str:
    explicit = item.get("report_family")
    if isinstance(explicit, str) and explicit:
        return explicit
    filename = str(item.get("filename") or "")
    return _family(Path(filename)) or "content_signature"


def _result_modified_at(item: dict) -> datetime | None:
    raw_value = item.get("source_modified_at")
    if not isinstance(raw_value, str) or not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _snapshot_scopes(analysis: dict) -> list[dict]:
    counts: dict[tuple[str, str], int] = {}
    for row in analysis.get("_rows", []):
        key = (row.account_external_id, row.metric_date.isoformat())
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "account_external_id": account_external_id,
            "metric_date": metric_date,
            "rows": rows,
        }
        for (account_external_id, metric_date), rows in sorted(counts.items())
    ]


def _scope_counts(item: dict) -> dict[tuple[str, str], int]:
    scopes = item.get("snapshot_scopes")
    if not isinstance(scopes, list):
        return {}
    result: dict[tuple[str, str], int] = {}
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        account_external_id = scope.get("account_external_id")
        metric_date = scope.get("metric_date")
        try:
            rows = int(scope.get("rows") or 0)
            date.fromisoformat(str(metric_date))
        except (TypeError, ValueError):
            continue
        if (
            not isinstance(account_external_id, str)
            or not account_external_id
            or rows < 0
        ):
            continue
        result[(account_external_id, str(metric_date))] = rows
    return result


def _confirmed_rows_read(file_results: list[dict]) -> int:
    latest_by_scope: dict[tuple[str, str], tuple[datetime, int]] = {}
    legacy_rows = 0
    for item in file_results:
        scopes = _scope_counts(item)
        if not scopes:
            legacy_rows += max(int(item.get("rows_read") or 0), 0)
            continue
        modified_at = _result_modified_at(item) or datetime.min.replace(tzinfo=UTC)
        for scope, rows in scopes.items():
            previous = latest_by_scope.get(scope)
            if previous is None or modified_at >= previous[0]:
                latest_by_scope[scope] = (modified_at, rows)
    return legacy_rows + sum(rows for _modified_at, rows in latest_by_scope.values())


def _protected_scope_times(file_results: list[dict]) -> dict[tuple[str, str], datetime]:
    protected: dict[tuple[str, str], datetime] = {}
    for item in file_results:
        modified_at = _result_modified_at(item)
        if modified_at is None:
            continue
        for scope in _scope_counts(item):
            previous = protected.get(scope)
            if previous is None or modified_at > previous:
                protected[scope] = modified_at
    return protected


def confirmed_results_from_metadata(metadata: dict) -> list[dict]:
    raw_results = metadata.get("confirmed_file_results")
    if not isinstance(raw_results, list):
        raw_results = metadata.get("file_results", [])
    return [
        dict(item)
        for item in raw_results
        if (
            isinstance(item, dict)
            and item.get("status") in CONFIRMED_STATUSES
            and isinstance(item.get("sha256"), str)
        )
    ]


def _latest_confirmation_state(db: Session) -> tuple[list[dict], str | None]:
    runs = db.scalars(
        select(SyncRun)
        .where(SyncRun.connector == CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    ).yield_per(100)
    for run in runs:
        results = confirmed_results_from_metadata(run.metadata_json)
        if not results:
            continue
        raw_timestamp = run.metadata_json.get("last_confirmed_at")
        if isinstance(raw_timestamp, str) and raw_timestamp:
            return results, raw_timestamp
        checked_values = sorted(
            str(item.get("checked_at"))
            for item in results
            if item.get("checked_at")
        )
        fallback = run.ended_at or run.started_at
        return results, (
            checked_values[-1]
            if checked_values
            else fallback.isoformat() if fallback else None
        )
    return [], None


def _previous_results(db: Session) -> dict[str, dict]:
    latest = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    if latest is None:
        return {}
    if latest.metadata_json.get("cache_version") != CACHE_VERSION:
        return {}
    by_hash = {
        item["sha256"]: item
        for item in confirmed_results_from_metadata(latest.metadata_json)
    }
    for item in latest.metadata_json.get("file_results", []):
        if (
            isinstance(item, dict)
            and isinstance(item.get("sha256"), str)
            and item.get("status") != "DUPLICATE_SKIPPED"
        ):
            by_hash[item["sha256"]] = item
    return by_hash


def import_downloaded_campaign_reports(
    db: Session,
    *,
    root: Path | None = None,
    now: datetime | None = None,
    min_age_seconds: int = 60,
) -> dict:
    now = now or datetime.now(UTC)
    discovery = _discover_campaign_report_inputs(
        root,
        now=now,
        min_age_seconds=min_age_seconds,
    )
    def candidate_sort_key(path: Path) -> tuple[int, bool, str]:
        try:
            modified_ns = path.stat().st_mtime_ns
        except OSError:
            modified_ns = -1
        return modified_ns, _family(path) is None, path.name

    candidates = sorted(discovery.reports, key=candidate_sort_key)
    previous_by_hash = _previous_results(db)
    previous_confirmed_results, previous_last_confirmed_at = (
        _latest_confirmation_state(db)
    )
    protected_scope_times = _protected_scope_times(previous_confirmed_results)
    accounts = list(db.scalars(select(AdsAccount).order_by(AdsAccount.id.asc())).all())
    fallback_id = accounts[0].external_id if len(accounts) == 1 else ""
    fallback_name = accounts[0].name if len(accounts) == 1 else "Google Ads CSV"

    file_results: list[dict] = []
    rows_read = 0
    rows_written = 0
    processed = 0
    unchanged = 0
    retried_after_error = 0
    retried_after_mapping = 0
    error_count = 0
    duplicate_skipped = 0
    superseded = 0
    account_mismatch = 0
    content_detected = sum(_family(path) is None for path in candidates)
    seen_digests: dict[str, str] = {}

    for path in candidates:
        digest = ""
        source_modified_at = now
        detection_method = (
            "CONTENT_SIGNATURE" if _family(path) is None else "FILENAME"
        )
        report_family = _family(path) or "content_signature"
        try:
            source_modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            data = path.read_bytes()
            digest = _sha256(data)
            duplicate_of = seen_digests.get(digest)
            if duplicate_of is not None:
                duplicate_skipped += 1
                file_results.append(
                    {
                        "filename": path.name,
                        "detection_method": detection_method,
                        "report_family": report_family,
                        "source_modified_at": source_modified_at.isoformat(),
                        "sha256": digest,
                        "status": "DUPLICATE_SKIPPED",
                        "checked_at": now.isoformat(),
                        "unchanged": True,
                        "duplicate_of": duplicate_of,
                        "retried_after_error": False,
                        "retried_after_mapping": False,
                        "rows_read": 0,
                        "rows_written": 0,
                        "mapped_rows": 0,
                        "unmapped_rows": 0,
                        "auto_mapped_rows": 0,
                        "metric_date_from": None,
                        "metric_date_to": None,
                        "error": None,
                    }
                )
                continue
            seen_digests[digest] = path.name
            previous = previous_by_hash.get(digest)
            previous_was_error = bool(
                previous is not None
                and previous.get("status") in {"ERROR", "ACCOUNT_MISMATCH"}
            )
            previous_had_unmapped = bool(
                previous is not None
                and not previous_was_error
                and int(previous.get("unmapped_rows") or 0) > 0
            )
            if previous is not None and not previous_was_error and not previous_had_unmapped:
                carried = dict(previous)
                carried.update(
                    {
                        "filename": path.name,
                        "detection_method": detection_method,
                        "report_family": report_family,
                        "source_modified_at": source_modified_at.isoformat(),
                        "checked_at": now.isoformat(),
                        "unchanged": True,
                    }
                )
                file_results.append(carried)
                unchanged += 1
                if carried.get("status") == "ERROR":
                    error_count += 1
                continue
            if previous_was_error:
                retried_after_error += 1
            elif previous_had_unmapped:
                retried_after_mapping += 1

            analysis = analyze_campaign_import(
                db,
                data,
                "GOOGLE_ADS_CSV_AUTO",
                fallback_id,
                fallback_name,
                None,
            )
            processed += 1
            rows_read += analysis["rows_read"]
            snapshot_scopes = _snapshot_scopes(analysis)
            signature = inspect_campaign_report_signature(data)
            account_identity = _campaign_report_account_identity(
                analysis,
                accounts,
                has_customer_id_column=bool(
                    signature.get("has_customer_id_column")
                ),
            )
            if analysis.get("_identity_rows") and not account_identity["allowed"]:
                account_mismatch += 1
                error_count += 1
                file_results.append(
                    {
                        "filename": path.name,
                        "detection_method": detection_method,
                        "report_family": report_family,
                        "source_modified_at": source_modified_at.isoformat(),
                        "sha256": digest,
                        "status": "ACCOUNT_MISMATCH",
                        "checked_at": now.isoformat(),
                        "unchanged": False,
                        "retried_after_error": previous_was_error,
                        "retried_after_mapping": previous_had_unmapped,
                        "rows_read": analysis["rows_read"],
                        "rows_written": 0,
                        "mapped_rows": analysis["mapped_rows"],
                        "unmapped_rows": analysis["unmapped_rows"],
                        "auto_mapped_rows": analysis["auto_mapped_rows"],
                        "campaign_id_resolution": analysis[
                            "campaign_id_resolution"
                        ],
                        "metric_date_from": (
                            analysis["metric_date_from"].isoformat()
                            if analysis["metric_date_from"]
                            else None
                        ),
                        "metric_date_to": (
                            analysis["metric_date_to"].isoformat()
                            if analysis["metric_date_to"]
                            else None
                        ),
                        "snapshot_scopes": snapshot_scopes,
                        "account_identity": account_identity,
                        "error": account_identity["error"],
                    }
                )
                continue
            if analysis["error_count"] or analysis["valid_rows"] == 0:
                error_count += 1
                file_results.append(
                    {
                        "filename": path.name,
                        "detection_method": detection_method,
                        "report_family": report_family,
                        "source_modified_at": source_modified_at.isoformat(),
                        "sha256": digest,
                        "status": "ERROR",
                        "checked_at": now.isoformat(),
                        "unchanged": False,
                        "retried_after_error": previous_was_error,
                        "retried_after_mapping": previous_had_unmapped,
                        "rows_read": analysis["rows_read"],
                        "rows_written": 0,
                        "mapped_rows": analysis["mapped_rows"],
                        "unmapped_rows": analysis["unmapped_rows"],
                        "auto_mapped_rows": analysis["auto_mapped_rows"],
                        "campaign_id_resolution": analysis[
                            "campaign_id_resolution"
                        ],
                        "metric_date_from": (
                            analysis["metric_date_from"].isoformat()
                            if analysis["metric_date_from"]
                            else None
                        ),
                        "metric_date_to": (
                            analysis["metric_date_to"].isoformat()
                            if analysis["metric_date_to"]
                            else None
                        ),
                        "error": (
                            analysis["errors"][0]["message"]
                            if analysis["errors"]
                            else "Báo cáo không có dòng campaign hợp lệ"
                        ),
                        "snapshot_scopes": snapshot_scopes,
                        "account_identity": account_identity,
                    }
                )
                continue

            protected_by_newer_snapshot = any(
                protected_scope_times.get(
                    (scope["account_external_id"], scope["metric_date"])
                )
                is not None
                and protected_scope_times[
                    (scope["account_external_id"], scope["metric_date"])
                ]
                > source_modified_at
                for scope in snapshot_scopes
            )
            if protected_by_newer_snapshot:
                superseded += 1
                file_results.append(
                    {
                        "filename": path.name,
                        "detection_method": detection_method,
                        "report_family": report_family,
                        "source_modified_at": source_modified_at.isoformat(),
                        "sha256": digest,
                        "status": "SUPERSEDED",
                        "checked_at": now.isoformat(),
                        "unchanged": False,
                        "retried_after_error": previous_was_error,
                        "retried_after_mapping": previous_had_unmapped,
                        "rows_read": analysis["rows_read"],
                        "rows_written": 0,
                        "rows_superseded": analysis["valid_rows"],
                        "mapped_rows": analysis["mapped_rows"],
                        "unmapped_rows": analysis["unmapped_rows"],
                        "auto_mapped_rows": analysis["auto_mapped_rows"],
                        "campaign_id_resolution": analysis[
                            "campaign_id_resolution"
                        ],
                        "metric_date_from": analysis["metric_date_from"].isoformat(),
                        "metric_date_to": analysis["metric_date_to"].isoformat(),
                        "snapshot_scopes": snapshot_scopes,
                        "account_identity": account_identity,
                        "error": None,
                    }
                )
                continue

            written = commit_campaign_import(db, analysis, actor="auto-folder")
            rows_written += written
            file_results.append(
                {
                    "filename": path.name,
                    "detection_method": detection_method,
                    "report_family": report_family,
                    "source_modified_at": source_modified_at.isoformat(),
                    "sha256": digest,
                    "status": "IMPORTED" if written else "UP_TO_DATE",
                    "checked_at": now.isoformat(),
                    "unchanged": False,
                    "retried_after_error": previous_was_error,
                    "retried_after_mapping": previous_had_unmapped,
                    "rows_read": analysis["rows_read"],
                    "rows_written": written,
                    "mapped_rows": analysis["mapped_rows"],
                    "unmapped_rows": analysis["unmapped_rows"],
                    "auto_mapped_rows": analysis["auto_mapped_rows"],
                    "campaign_id_resolution": analysis[
                        "campaign_id_resolution"
                    ],
                    "metric_date_from": analysis["metric_date_from"].isoformat(),
                    "metric_date_to": analysis["metric_date_to"].isoformat(),
                    "snapshot_scopes": snapshot_scopes,
                    "account_identity": account_identity,
                    "error": None,
                }
            )
            for scope in snapshot_scopes:
                protected_scope_times[
                    (scope["account_external_id"], scope["metric_date"])
                ] = source_modified_at
        except (OSError, SQLAlchemyError, ValueError) as exc:
            db.rollback()
            error_count += 1
            processed += 1
            file_results.append(
                {
                    "filename": path.name,
                    "detection_method": detection_method,
                    "report_family": report_family,
                    "source_modified_at": source_modified_at.isoformat(),
                    "sha256": digest,
                    "status": "ERROR",
                    "checked_at": now.isoformat(),
                    "unchanged": False,
                    "retried_after_error": bool(
                        digest
                        and previous_by_hash.get(digest, {}).get("status")
                        in {"ERROR", "ACCOUNT_MISMATCH"}
                    ),
                    "retried_after_mapping": bool(
                        digest
                        and previous_by_hash.get(digest, {}).get("status") != "ERROR"
                        and int(
                            previous_by_hash.get(digest, {}).get("unmapped_rows") or 0
                        )
                        > 0
                    ),
                    "rows_read": 0,
                    "rows_written": 0,
                    "mapped_rows": 0,
                    "unmapped_rows": 0,
                    "auto_mapped_rows": 0,
                    "metric_date_from": None,
                    "metric_date_to": None,
                    "error": str(exc),
                }
            )

    confirmed_by_family = {
        _result_family(item): dict(item) for item in previous_confirmed_results
    }
    current_confirmed = False
    for item in file_results:
        if item.get("status") not in CONFIRMED_STATUSES:
            continue
        family = _result_family(item)
        previous = confirmed_by_family.get(family)
        previous_modified_at = _result_modified_at(previous or {})
        item_modified_at = _result_modified_at(item)
        if (
            previous is None
            or previous_modified_at is None
            or item_modified_at is None
            or item_modified_at >= previous_modified_at
        ):
            confirmed_by_family[family] = dict(item)
        current_confirmed = True
    confirmed_file_results = [
        confirmed_by_family[family] for family in sorted(confirmed_by_family)
    ]
    last_confirmed_at = (
        now.isoformat() if current_confirmed else previous_last_confirmed_at
    )

    status = SyncStatus.PARTIAL if error_count else SyncStatus.SUCCESS
    report = {
        "status": status.value,
        "cache_version": CACHE_VERSION,
        "input_folder": "~/Downloads",
        "files_seen": len(candidates),
        "files_content_detected": content_detected,
        "files_duplicate_skipped": duplicate_skipped,
        "files_superseded": superseded,
        "files_account_mismatch": account_mismatch,
        "files_missing_columns": len(discovery.rejected_candidates),
        "rejected_candidates": discovery.rejected_candidates,
        "confirmed_file_count": len(confirmed_file_results),
        "confirmed_file_results": confirmed_file_results,
        "confirmed_rows_read": _confirmed_rows_read(confirmed_file_results),
        "last_confirmed_at": last_confirmed_at,
        "files_processed": processed,
        "files_unchanged": unchanged,
        "files_retried_after_error": retried_after_error,
        "files_retried_after_mapping": retried_after_mapping,
        "rows_read": rows_read,
        "rows_written": rows_written,
        "error_count": error_count,
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
                    if item.get("status") in {"ERROR", "ACCOUNT_MISMATCH"}
                )
                or None
            ),
            metadata_json=report,
        )
    )
    db.commit()
    return report
