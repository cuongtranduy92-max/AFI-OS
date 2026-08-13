from __future__ import annotations

import argparse
import fcntl
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.config import get_settings
from afi_os.db import SessionLocal
from afi_os.enums import SyncStatus
from afi_os.models import Program, SyncRun, TermsResearchRun
from afi_os.services.ads_folder_import import import_downloaded_campaign_reports
from afi_os.services.automation_queue import queue_summary, run_terms_research_job
from afi_os.services.backups import backup_is_verified, create_backup, list_backups
from afi_os.services.campaign_import import backfill_campaign_domain_mappings
from afi_os.services.commission_folder_import import (
    import_downloaded_commission_reports,
)
from afi_os.services.currency import apply_currency_normalization
from afi_os.services.google_ads_api_sync import (
    clear_google_ads_api_sync_request,
    google_ads_api_sync_due_at,
    google_ads_api_sync_is_due,
    google_ads_api_sync_requested,
    sync_google_ads_api,
)
from afi_os.services.operations import operations_inbox
from afi_os.services.programs import (
    TERMS_SCHEDULE_GRACE,
    latest_research_run,
    research_refresh_due_at,
)
from afi_os.services.project_sync import sync_program_projects
from afi_os.services.terms_research import collect_domain_proposal
from afi_os.services.truth_repairs import repair_automated_truth_semantics

BACKUP_INTERVAL = timedelta(hours=24)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError, AttributeError):
        return None


def backup_is_due(backups: list[dict], now: datetime) -> bool:
    scheduled = [
        item
        for item in backups
        if item.get("name", "").startswith("scheduled-")
        and backup_is_verified(item)
    ]
    timestamps = [_parse_timestamp(item.get("created_at")) for item in scheduled]
    valid = [item for item in timestamps if item is not None]
    return not valid or max(valid) < now - BACKUP_INTERVAL


def terms_refresh_is_due(
    db: Session,
    domain: str,
    now: datetime,
) -> bool:
    runs = db.scalars(
        select(TermsResearchRun)
        .where(TermsResearchRun.domain == domain)
    ).all()
    latest = latest_research_run(runs)
    if latest is None:
        return True
    return research_refresh_due_at(latest) <= _aware(now) + TERMS_SCHEDULE_GRACE


def run_maintenance(
    db: Session,
    *,
    now: datetime | None = None,
    collector: Callable = collect_domain_proposal,
    backup_creator: Callable = create_backup,
    backup_lister: Callable = list_backups,
    ads_api_syncer: Callable = sync_google_ads_api,
    campaign_mapper: Callable = backfill_campaign_domain_mappings,
    force_google_ads_api: bool = False,
) -> dict:
    now = _aware(now or datetime.now(UTC))
    sync = SyncRun(
        connector="AFI_OS_MAINTENANCE",
        started_at=now,
        status=SyncStatus.RUNNING,
        rows_read=0,
        rows_written=0,
        metadata_json={},
    )
    db.add(sync)
    db.commit()
    db.refresh(sync)

    report: dict = {
        "started_at": now.isoformat(),
        "backup": None,
        "terms_checked": [],
        "terms_skipped_fresh": [],
        "terms_deferred_queue": [],
        "ads_import": None,
        "ads_api_sync": None,
        "commission_import": None,
        "campaign_auto_map": None,
        "normalization": None,
        "operations": None,
        "automation_queue": None,
        "project_sync": None,
        "truth_semantic_repair": None,
        "errors": [],
    }

    try:
        report["truth_semantic_repair"] = repair_automated_truth_semantics(db)
        db.commit()
        sync.rows_written += report["truth_semantic_repair"]["evidence_repaired"]
        sync.rows_written += report["truth_semantic_repair"]["facts_repaired"]
    except Exception as exc:
        db.rollback()
        report["errors"].append(
            f"truth_semantic_repair: {type(exc).__name__}: {exc}"
        )

    try:
        report["project_sync"] = sync_program_projects(
            db,
            actor="maintenance-project-sync-v1",
        )
        db.commit()
        sync.rows_written += report["project_sync"]["created"] + report[
            "project_sync"
        ]["linked"]
    except Exception as exc:
        db.rollback()
        report["errors"].append(f"project_sync: {type(exc).__name__}: {exc}")

    try:
        if backup_is_due(backup_lister(), now):
            report["backup"] = backup_creator(prefix="scheduled")
    except Exception as exc:  # maintenance continues and reports the exception
        report["errors"].append(f"backup: {type(exc).__name__}: {exc}")

    programs = list(db.scalars(select(Program).order_by(Program.id.asc())).all())
    sync.rows_read = len(programs)
    for program in programs:
        domain = program.merchant.website_domain
        if not terms_refresh_is_due(db, domain, now):
            report["terms_skipped_fresh"].append(domain)
            continue
        try:
            latest = latest_research_run(
                list(
                    db.scalars(
                        select(TermsResearchRun).where(
                            TermsResearchRun.domain == domain
                        )
                    ).all()
                )
            )
            due_at = (
                research_refresh_due_at(latest)
                if latest is not None
                else program.created_at
            )
            job, result = run_terms_research_job(
                db,
                program,
                due_at=due_at,
                collector=collector,
                now=now,
            )
            if result is None:
                report["terms_deferred_queue"].append(
                    {
                        "domain": domain,
                        "job_id": job.id,
                        "status": job.status.value,
                        "run_after": job.run_after.isoformat(),
                    }
                )
                continue
            if "run" in result:
                checked = {
                    "domain": domain,
                    "status": result["run"].status.value,
                    "imported_terms_evidence": result.get("imported_evidence", 0),
                    "imported_commission_facts": result.get("imported", 0),
                    "permissions_changed": False,
                    "automation_job_id": job.id,
                }
            else:
                checked = {
                    "domain": domain,
                    **result,
                    "automation_job_id": job.id,
                }
            report["terms_checked"].append(checked)
            sync.rows_written += int(checked.get("imported_terms_evidence", 0)) + int(
                checked.get("imported_commission_facts", 0)
            )
        except Exception as exc:  # one merchant must not stop all maintenance
            db.rollback()
            report["errors"].append(
                f"terms:{domain}: {type(exc).__name__}: {exc}"
            )

    if get_settings().env.lower() == "production":
        try:
            report["ads_import"] = import_downloaded_campaign_reports(db, now=now)
            sync.rows_read += report["ads_import"]["rows_read"]
            sync.rows_written += report["ads_import"]["rows_written"]
        except Exception as exc:
            db.rollback()
            report["errors"].append(f"ads_import: {type(exc).__name__}: {exc}")
        api_request_pending = google_ads_api_sync_requested()
        api_attempted = False
        try:
            if force_google_ads_api or api_request_pending or google_ads_api_sync_is_due(
                db,
                now=now,
            ):
                api_attempted = True
                report["ads_api_sync"] = ads_api_syncer(db, now=now)
            else:
                report["ads_api_sync"] = {
                    "status": "SKIPPED_FRESH",
                    "next_attempt_at": google_ads_api_sync_due_at(
                        db,
                        now=now,
                    ).isoformat(),
                    "rows_read": 0,
                    "rows_written": 0,
                    "write_operations_enabled": False,
                    "csv_fallback_enabled": True,
                }
            sync.rows_read += report["ads_api_sync"]["rows_read"]
            sync.rows_written += report["ads_api_sync"]["rows_written"]
        except Exception as exc:
            db.rollback()
            report["errors"].append(
                f"ads_api_sync: {type(exc).__name__}: {exc}"
            )
        finally:
            if api_request_pending and api_attempted:
                try:
                    clear_google_ads_api_sync_request()
                except OSError as exc:
                    report["errors"].append(
                        f"ads_api_sync_request: {type(exc).__name__}: {exc}"
                    )
        try:
            report["commission_import"] = import_downloaded_commission_reports(
                db,
                now=now,
            )
            sync.rows_read += report["commission_import"]["rows_read"]
            sync.rows_written += report["commission_import"]["rows_written"]
        except Exception as exc:
            db.rollback()
            report["errors"].append(
                f"commission_import: {type(exc).__name__}: {exc}"
            )
    else:
        report["ads_import"] = {"status": "DISABLED_NON_PRODUCTION"}
        report["ads_api_sync"] = {"status": "DISABLED_NON_PRODUCTION"}
        report["commission_import"] = {"status": "DISABLED_NON_PRODUCTION"}

    try:
        report["campaign_auto_map"] = campaign_mapper(db)
        sync.rows_read += report["campaign_auto_map"]["unlinked_scanned"]
        sync.rows_written += report["campaign_auto_map"]["mapped"]
    except Exception as exc:
        db.rollback()
        report["errors"].append(
            f"campaign_auto_map: {type(exc).__name__}: {exc}"
        )

    try:
        report["normalization"] = apply_currency_normalization(db)
        db.commit()
    except Exception as exc:
        db.rollback()
        report["errors"].append(f"normalization: {type(exc).__name__}: {exc}")

    try:
        inbox = operations_inbox(db)
        report["operations"] = {
            "open_count": inbox["open_count"],
            "requires_user_count": inbox["requires_user_count"],
            "warning_count": inbox["warning_count"],
            "counts_by_type": inbox["counts_by_type"],
        }
    except Exception as exc:
        db.rollback()
        report["errors"].append(f"operations: {type(exc).__name__}: {exc}")

    try:
        report["automation_queue"] = queue_summary(db, now=now)
    except Exception as exc:
        db.rollback()
        report["errors"].append(
            f"automation_queue: {type(exc).__name__}: {exc}"
        )

    ended_at = datetime.now(UTC)
    sync = db.get(SyncRun, sync.id)
    sync.ended_at = ended_at
    sync.status = SyncStatus.PARTIAL if report["errors"] else SyncStatus.SUCCESS
    sync.error_summary = "\n".join(report["errors"]) or None
    sync.metadata_json = report
    db.commit()
    report["ended_at"] = ended_at.isoformat()
    report["sync_status"] = sync.status.value
    return report


@contextmanager
def maintenance_lock() -> Iterator[bool]:
    root = get_settings().project_root
    lock_path = root / "logs" / "maintenance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one safe AFI-OS maintenance cycle")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--force-google-ads-api", action="store_true")
    args = parser.parse_args()
    with maintenance_lock() as acquired:
        if not acquired:
            print(json.dumps({"status": "SKIPPED", "reason": "maintenance already running"}))
            return
        with SessionLocal() as db:
            report = run_maintenance(
                db,
                force_google_ads_api=args.force_google_ads_api,
            )
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
