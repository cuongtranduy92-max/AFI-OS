from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from afi_os.enums import ResearchStatus, SyncStatus
from afi_os.models import Program, SyncRun, TermsResearchRun
from afi_os.services.ads_folder_import import (
    INTRADAY_REPORT_MAX_AGE,
    ads_report_intraday_refresh_due,
    confirmed_results_from_metadata,
    latest_metric_date,
    latest_report_source_at,
)
from afi_os.services.backups import backup_is_verified, list_backups
from afi_os.services.google_ads_api_sync import CONNECTOR as GOOGLE_ADS_API_CONNECTOR
from afi_os.services.google_ads_api_sync import (
    google_ads_api_sync_due_at,
    google_ads_api_sync_requested,
)
from afi_os.services.google_ads_readiness import google_ads_readiness
from afi_os.services.programs import (
    TERMS_SCHEDULE_GRACE,
    latest_research_runs_by_domain,
    program_gate_status,
    research_attempted_at,
    research_refresh_due_at,
)

SERVER_LABEL = "com.afi-os.server"
MAINTENANCE_LABEL = "com.afi-os.maintenance"
MAINTENANCE_INTERVAL = timedelta(minutes=30)
MAINTENANCE_GRACE = timedelta(minutes=20)
BACKUP_INTERVAL = timedelta(hours=24)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_timestamp(value: str | None) -> datetime | None:
    try:
        return _aware(datetime.fromisoformat((value or "").replace("Z", "+00:00")))
    except (TypeError, ValueError, AttributeError):
        return None


def _next_scheduled_terms_refresh(
    eligible_at: datetime,
    maintenance_due_at: datetime | None,
    now: datetime,
) -> datetime:
    """Return the first slot within the small scheduling grace before eligibility."""
    eligible_at = _aware(eligible_at)
    now = _aware(now)
    if maintenance_due_at is None:
        return max(eligible_at, now)
    threshold = max(eligible_at - TERMS_SCHEDULE_GRACE, now)
    scheduled = _aware(maintenance_due_at)
    if scheduled >= threshold:
        return scheduled
    elapsed = threshold - scheduled
    steps = elapsed // MAINTENANCE_INTERVAL
    candidate = scheduled + steps * MAINTENANCE_INTERVAL
    return candidate if candidate >= threshold else candidate + MAINTENANCE_INTERVAL


def launchd_service_loaded(label: str) -> bool:
    if label not in {SERVER_LABEL, MAINTENANCE_LABEL}:
        return False
    executable = Path("/bin/launchctl")
    if not executable.is_file():
        return False
    try:
        result = subprocess.run(
            [str(executable), "print", f"gui/{os.getuid()}/{label}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def runtime_status(
    db: Session,
    *,
    now: datetime | None = None,
    service_checker: Callable[[str], bool] = launchd_service_loaded,
    backup_lister: Callable[[], list[dict]] = list_backups,
) -> dict:
    now = _aware(now or datetime.now(UTC))
    server_loaded = service_checker(SERVER_LABEL)
    maintenance_loaded = service_checker(MAINTENANCE_LABEL)

    latest_sync = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == "AFI_OS_MAINTENANCE")
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    maintenance_metadata = latest_sync.metadata_json if latest_sync else {}
    campaign_auto_map = maintenance_metadata.get("campaign_auto_map") or {}
    last_started_at = _aware(latest_sync.started_at) if latest_sync else None
    last_ended_at = (
        _aware(latest_sync.ended_at) if latest_sync and latest_sync.ended_at else None
    )
    next_maintenance_due_at = (
        last_started_at + MAINTENANCE_INTERVAL if last_started_at else None
    )
    maintenance_overdue = bool(
        next_maintenance_due_at
        and now > next_maintenance_due_at + MAINTENANCE_GRACE
    )
    latest_ads_import = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == "GOOGLE_ADS_FOLDER")
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    ads_metadata = latest_ads_import.metadata_json if latest_ads_import else {}
    ads_confirmed_file_results = confirmed_results_from_metadata(ads_metadata)
    ads_csv_error_count = int(ads_metadata.get("error_count") or 0)
    confirmed_rows_read = ads_metadata.get("confirmed_rows_read")
    ads_rows_in_reports = (
        max(int(confirmed_rows_read), 0)
        if isinstance(confirmed_rows_read, int)
        else sum(
            int(item.get("rows_read") or 0)
            for item in ads_confirmed_file_results
            if isinstance(item, dict)
        )
    )
    ads_campaign_ids_recovered = sum(
        max(
            int(
                (item.get("campaign_id_resolution") or {}).get("resolved_rows")
                or 0
            ),
            0,
        )
        for item in ads_confirmed_file_results
        if isinstance(item, dict)
        and isinstance(item.get("campaign_id_resolution"), dict)
    )
    ads_csv_latest_date = latest_metric_date(ads_confirmed_file_results)
    ads_latest_report_source_at = latest_report_source_at(
        ads_confirmed_file_results
    )
    ads_last_confirmed_at = _parse_timestamp(
        ads_metadata.get("last_confirmed_at")
    )
    if ads_last_confirmed_at is None:
        confirmed_timestamps = [
            _parse_timestamp(item.get("checked_at"))
            for item in ads_confirmed_file_results
            if isinstance(item, dict)
        ]
        ads_last_confirmed_at = max(
            (item for item in confirmed_timestamps if item is not None),
            default=None,
        )
    latest_commission_import = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == "AFFILIATE_COMMISSION_FOLDER")
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    commission_metadata = (
        latest_commission_import.metadata_json if latest_commission_import else {}
    )
    commission_file_results = commission_metadata.get("file_results", [])
    commission_rows_in_reports = sum(
        int(item.get("rows_read") or 0)
        for item in commission_file_results
        if isinstance(item, dict)
    )
    commission_error_count = int(commission_metadata.get("error_count") or 0)
    commission_mapping_required_count = int(
        commission_metadata.get("mapping_required_count") or 0
    )
    api_readiness = google_ads_readiness(db)
    latest_ads_api_sync = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == GOOGLE_ADS_API_CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    ads_api_metadata = latest_ads_api_sync.metadata_json if latest_ads_api_sync else {}
    ads_api_reconciliation = ads_api_metadata.get("reconciliation_before_commit", {})
    ads_api_request_pending = google_ads_api_sync_requested()
    ads_api_next_attempt_at = None
    ads_api_sync_due = False
    if api_readiness["status"] == "READY":
        ads_api_next_attempt_at = (
            now
            if ads_api_request_pending
            else google_ads_api_sync_due_at(db, now=now)
        )
        ads_api_sync_due = ads_api_next_attempt_at <= now
    ads_api_latest_date = None
    if latest_ads_api_sync and latest_ads_api_sync.status == SyncStatus.SUCCESS:
        try:
            ads_api_latest_date = date.fromisoformat(str(ads_api_metadata.get("date_to")))
        except ValueError:
            pass
    confirmed_ads_dates = [
        item for item in (ads_csv_latest_date, ads_api_latest_date) if item is not None
    ]
    ads_latest_date = max(confirmed_ads_dates, default=None)
    ads_data_stale = bool(
        ads_latest_date and ads_latest_date < now.date() - timedelta(days=1)
    )
    ads_api_is_fresh = bool(
        ads_api_latest_date
        and ads_api_latest_date >= now.date() - timedelta(days=1)
    )
    ads_api_has_today = ads_api_latest_date == now.date()
    ads_intraday_refresh_due = bool(
        not ads_api_has_today
        and ads_report_intraday_refresh_due(
            ads_confirmed_file_results,
            now=now,
        )
    )
    ads_next_intraday_refresh_at = (
        ads_latest_report_source_at + INTRADAY_REPORT_MAX_AGE
        if ads_latest_report_source_at is not None
        and ads_csv_latest_date == now.date()
        and not ads_api_has_today
        else None
    )
    ads_error_count = 0 if ads_api_is_fresh else ads_csv_error_count
    ads_missing_columns_count = (
        0
        if ads_api_is_fresh
        else int(ads_metadata.get("files_missing_columns") or 0)
    )

    all_scheduled_backups = [
        item for item in backup_lister() if item.get("name", "").startswith("scheduled-")
    ]
    scheduled_backups = [
        item for item in all_scheduled_backups if backup_is_verified(item)
    ]
    scheduled_backups.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    latest_backup = scheduled_backups[0] if scheduled_backups else None
    latest_backup_at = _parse_timestamp(latest_backup.get("created_at")) if latest_backup else None
    next_backup_due_at = latest_backup_at + BACKUP_INTERVAL if latest_backup_at else now
    scheduled_backup_due = latest_backup_at is None or next_backup_due_at <= now
    scheduled_backup_invalid_count = len(all_scheduled_backups) - len(scheduled_backups)

    programs = list(
        db.scalars(
            select(Program).options(
                selectinload(Program.merchant),
                selectinload(Program.terms_evidence),
                selectinload(Program.terms_research_runs),
            )
        ).all()
    )
    latest_research_by_domain = latest_research_runs_by_domain(
        db.scalars(select(TermsResearchRun)).all()
    )
    terms_fresh = 0
    terms_due_count = 0
    terms_retry_pending = 0
    terms_refresh_times: list[datetime] = []
    for program in programs:
        domain = program.merchant.website_domain
        run = latest_research_by_domain.get(domain)
        last_attempt = _aware(research_attempted_at(run)) if run else None
        refresh_at = research_refresh_due_at(run) if run else now
        terms_refresh_times.append(refresh_at)
        if run and run.status == ResearchStatus.RETRY_REQUIRED:
            terms_retry_pending += 1
        if last_attempt and refresh_at > now:
            terms_fresh += 1
        else:
            terms_due_count += 1
    terms_stale = len(programs) - terms_fresh
    terms_next_refresh_at = min(terms_refresh_times, default=None)
    terms_next_scheduled_refresh_at = (
        _next_scheduled_terms_refresh(
            terms_next_refresh_at,
            next_maintenance_due_at,
            now,
        )
        if terms_next_refresh_at
        else None
    )
    programs_terms_ok = sum(
        program_gate_status(program, list(program.terms_evidence)) == "TERMS_OK"
        for program in programs
    )
    programs_terms_warnings = len(programs) - programs_terms_ok

    if not server_loaded and not maintenance_loaded:
        status = "NOT_CONFIGURED"
    elif not server_loaded or not maintenance_loaded:
        status = "ATTENTION"
    elif latest_sync is None:
        status = "STARTING"
    elif (
        latest_sync.status != SyncStatus.SUCCESS
        or maintenance_overdue
        or ads_error_count > 0
        or ads_missing_columns_count > 0
        or ads_data_stale
        or ads_intraday_refresh_due
        or commission_error_count > 0
        or commission_mapping_required_count > 0
        or scheduled_backup_due
    ):
        status = "ATTENTION"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "server_service_loaded": server_loaded,
        "maintenance_service_loaded": maintenance_loaded,
        "maintenance_status": latest_sync.status.value if latest_sync else None,
        "maintenance_last_started_at": last_started_at,
        "maintenance_last_ended_at": last_ended_at,
        "maintenance_next_due_at": next_maintenance_due_at,
        "maintenance_overdue": maintenance_overdue,
        "maintenance_rows_read": latest_sync.rows_read if latest_sync else 0,
        "maintenance_rows_written": latest_sync.rows_written if latest_sync else 0,
        "maintenance_error": latest_sync.error_summary if latest_sync else None,
        "campaign_auto_map_total": int(
            campaign_auto_map.get("campaigns_total") or 0
        ),
        "campaign_auto_map_unlinked_scanned": int(
            campaign_auto_map.get("unlinked_scanned") or 0
        ),
        "campaign_auto_map_mapped": int(campaign_auto_map.get("mapped") or 0),
        "campaign_auto_map_unresolved": int(
            campaign_auto_map.get("unresolved") or 0
        ),
        "campaign_auto_map_preserved_existing": int(
            campaign_auto_map.get("preserved_existing") or 0
        ),
        "ads_import_status": (
            latest_ads_import.status.value if latest_ads_import else None
        ),
        "ads_import_last_at": (
            _aware(latest_ads_import.ended_at or latest_ads_import.started_at)
            if latest_ads_import
            else None
        ),
        "ads_files_seen": int(ads_metadata.get("files_seen") or 0),
        "ads_files_content_detected": int(
            ads_metadata.get("files_content_detected") or 0
        ),
        "ads_files_duplicate_skipped": int(
            ads_metadata.get("files_duplicate_skipped") or 0
        ),
        "ads_files_superseded": int(ads_metadata.get("files_superseded") or 0),
        "ads_files_account_mismatch": int(
            ads_metadata.get("files_account_mismatch") or 0
        ),
        "ads_files_missing_columns": ads_missing_columns_count,
        "ads_confirmed_file_count": len(ads_confirmed_file_results),
        "ads_last_confirmed_at": ads_last_confirmed_at,
        "ads_files_retried_after_error": int(
            ads_metadata.get("files_retried_after_error") or 0
        ),
        "ads_files_retried_after_mapping": int(
            ads_metadata.get("files_retried_after_mapping") or 0
        ),
        "ads_rows_read": ads_rows_in_reports,
        "ads_rows_written": latest_ads_import.rows_written if latest_ads_import else 0,
        "ads_campaign_ids_recovered": ads_campaign_ids_recovered,
        "ads_error_count": ads_error_count,
        "ads_latest_metric_date": ads_latest_date,
        "ads_data_stale": ads_data_stale,
        "ads_latest_report_source_at": ads_latest_report_source_at,
        "ads_intraday_refresh_due": ads_intraday_refresh_due,
        "ads_next_intraday_refresh_at": ads_next_intraday_refresh_at,
        "commission_import_status": (
            latest_commission_import.status.value
            if latest_commission_import
            else None
        ),
        "commission_import_last_at": (
            _aware(
                latest_commission_import.ended_at
                or latest_commission_import.started_at
            )
            if latest_commission_import
            else None
        ),
        "commission_files_seen": int(commission_metadata.get("files_seen") or 0),
        "commission_files_retried_after_error": int(
            commission_metadata.get("files_retried_after_error") or 0
        ),
        "commission_files_retried_after_mapping": int(
            commission_metadata.get("files_retried_after_mapping") or 0
        ),
        "commission_rows_read": commission_rows_in_reports,
        "commission_rows_written": (
            latest_commission_import.rows_written if latest_commission_import else 0
        ),
        "commission_error_count": commission_error_count,
        "commission_mapping_required_count": commission_mapping_required_count,
        "google_ads_api_status": api_readiness["status"],
        "google_ads_customer_ids": api_readiness.get("customer_ids", []),
        "google_ads_api_customer_count": api_readiness["customer_count"],
        "google_ads_api_missing_credentials": api_readiness["missing_credentials"],
        "google_ads_login_customer_id_configured": api_readiness.get(
            "login_customer_id_configured", False
        ),
        "google_ads_api_write_operations_enabled": api_readiness[
            "write_operations_enabled"
        ],
        "google_ads_api_sync_status": (
            latest_ads_api_sync.status.value if latest_ads_api_sync else None
        ),
        "google_ads_api_sync_last_at": (
            _aware(latest_ads_api_sync.ended_at or latest_ads_api_sync.started_at)
            if latest_ads_api_sync
            else None
        ),
        "google_ads_api_sync_due": ads_api_sync_due,
        "google_ads_api_next_attempt_at": ads_api_next_attempt_at,
        "google_ads_api_sync_request_pending": ads_api_request_pending,
        "google_ads_api_rows_read": latest_ads_api_sync.rows_read if latest_ads_api_sync else 0,
        "google_ads_api_rows_written": (
            latest_ads_api_sync.rows_written if latest_ads_api_sync else 0
        ),
        "google_ads_api_reconciliation_differences": int(
            ads_api_reconciliation.get("different_rows") or 0
        ),
        "latest_scheduled_backup_name": latest_backup.get("name") if latest_backup else None,
        "latest_scheduled_backup_at": latest_backup_at,
        "latest_scheduled_backup_size_bytes": (
            int(latest_backup.get("size_bytes") or 0) if latest_backup else None
        ),
        "scheduled_backup_due": scheduled_backup_due,
        "scheduled_backup_invalid_count": scheduled_backup_invalid_count,
        "next_backup_due_at": next_backup_due_at,
        "programs_total": len(programs),
        "terms_fresh": terms_fresh,
        "terms_stale": terms_stale,
        "terms_due_count": terms_due_count,
        "terms_retry_pending": terms_retry_pending,
        "terms_next_refresh_at": terms_next_refresh_at,
        "terms_next_scheduled_refresh_at": terms_next_scheduled_refresh_at,
        "programs_terms_ok": programs_terms_ok,
        "programs_terms_warnings": programs_terms_warnings,
    }
