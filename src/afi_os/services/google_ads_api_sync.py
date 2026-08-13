from __future__ import annotations

import csv
import io
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.config import get_settings
from afi_os.enums import SyncStatus
from afi_os.models import AdsAccount, SyncRun
from afi_os.services.campaign_import import (
    analyze_campaign_import,
    commit_campaign_import,
)
from afi_os.services.google_ads_api import (
    API_VERSION,
    GoogleAdsApiError,
    GoogleAdsCampaignMetric,
    refresh_access_token,
    search_campaign_metrics,
)
from afi_os.services.google_ads_keychain import credential_present, read_credential
from afi_os.services.google_ads_readiness import google_ads_readiness

CONNECTOR = "GOOGLE_ADS_API_READ_ONLY"
SOURCE = "GOOGLE_ADS_API"
LOOKBACK_DAYS = 7
SYNC_INTERVAL = timedelta(hours=6)
AUTH_RETRY_INTERVAL = timedelta(hours=24)
SYNC_REQUEST_FILENAME = "google-ads-api-sync.requested"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def latest_google_ads_api_sync(db: Session) -> SyncRun | None:
    return db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )


def google_ads_api_sync_due_at(
    db: Session,
    *,
    now: datetime | None = None,
) -> datetime:
    """Return the next allowed API attempt without affecting CSV fallback."""
    now = _aware(now or datetime.now(UTC))
    latest = latest_google_ads_api_sync(db)
    if latest is None:
        return now
    attempted_at = _aware(latest.ended_at or latest.started_at)
    interval = (
        AUTH_RETRY_INTERVAL
        if latest.status == SyncStatus.AUTH_FAILED
        else SYNC_INTERVAL
    )
    return attempted_at + interval


def google_ads_api_sync_is_due(
    db: Session,
    *,
    now: datetime | None = None,
) -> bool:
    now = _aware(now or datetime.now(UTC))
    return google_ads_api_sync_due_at(db, now=now) <= now


def google_ads_api_sync_request_path(project_root: Path | None = None) -> Path:
    root = Path(project_root or get_settings().project_root).expanduser().resolve()
    return root / "logs" / SYNC_REQUEST_FILENAME


def request_google_ads_api_sync(
    *,
    project_root: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Persist a secret-free one-shot request that survives launchd handoff."""
    path = google_ads_api_sync_request_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _aware(now or datetime.now(UTC)).isoformat().encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, timestamp)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    return path


def google_ads_api_sync_requested(*, project_root: Path | None = None) -> bool:
    path = google_ads_api_sync_request_path(project_root)
    return path.is_file() and not path.is_symlink()


def clear_google_ads_api_sync_request(*, project_root: Path | None = None) -> None:
    google_ads_api_sync_request_path(project_root).unlink(missing_ok=True)


def _normalized_customer_id(value: str) -> str | None:
    normalized = value.replace("-", "").strip()
    return normalized if len(normalized) == 10 and normalized.isdigit() else None


def _metrics_csv(metrics: list[GoogleAdsCampaignMetric]) -> bytes:
    output = io.StringIO(newline="")
    fieldnames = [
        "customer_id",
        "account_name",
        "campaign_id",
        "campaign",
        "campaign_status",
        "campaign_type",
        "currency_code",
        "date",
        "cost",
        "impressions",
        "clicks",
        "conversions",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for metric in metrics:
        writer.writerow(
            {
                "customer_id": metric.account_external_id,
                "account_name": metric.account_name,
                "campaign_id": metric.campaign_external_id,
                "campaign": metric.campaign_name,
                "campaign_status": metric.campaign_status,
                "campaign_type": metric.channel_type,
                "currency_code": metric.currency,
                "date": metric.metric_date.isoformat(),
                "cost": str(metric.cost),
                "impressions": metric.impressions,
                "clicks": metric.clicks,
                "conversions": str(metric.conversions),
            }
        )
    return output.getvalue().encode("utf-8")


def _account_map(db: Session) -> dict[str, AdsAccount]:
    output: dict[str, AdsAccount] = {}
    for account in db.scalars(select(AdsAccount).order_by(AdsAccount.id.asc())).all():
        normalized = _normalized_customer_id(account.external_id)
        if normalized is None:
            continue
        if normalized in output:
            raise GoogleAdsApiError("Có hai Google Ads account trùng Customer ID")
        output[normalized] = account
    return output


def _sync_google_ads_api(
    db: Session,
    *,
    now: datetime | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    commit: bool = True,
    credential_checker: Callable[[str], bool] = credential_present,
    credential_reader: Callable[[str], str] = read_credential,
    token_refresher: Callable = refresh_access_token,
    metrics_searcher: Callable = search_campaign_metrics,
) -> dict:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    readiness = google_ads_readiness(db, credential_checker=credential_checker)
    if readiness["status"] != "READY":
        return {
            "status": "SKIPPED_CREDENTIALS",
            "mode": "READ_ONLY_REPORTING",
            "api_version": API_VERSION,
            "missing_credentials": readiness["missing_credentials"],
            "rows_read": 0,
            "rows_written": 0,
            "csv_fallback_enabled": True,
            "write_operations_enabled": False,
        }

    accounts = _account_map(db)
    expected_ids = set(readiness["customer_ids"])
    if not expected_ids or expected_ids != set(accounts):
        raise GoogleAdsApiError("Google Ads account trong database không nhất quán")

    effective_end = end_date or (now.date() - timedelta(days=1))
    effective_start = start_date or (
        effective_end - timedelta(days=LOOKBACK_DAYS - 1)
    )
    client_id = credential_reader("oauth-client-id")
    client_secret = credential_reader("oauth-client-secret")
    refresh_token = credential_reader("refresh-token")
    developer_token = credential_reader("developer-token")
    login_customer_id = (
        credential_reader("login-customer-id")
        if credential_checker("login-customer-id")
        else None
    )
    access_token = token_refresher(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )

    all_metrics: list[GoogleAdsCampaignMetric] = []
    for normalized_id in sorted(accounts):
        account = accounts[normalized_id]
        metrics = metrics_searcher(
            customer_id=normalized_id,
            access_token=access_token,
            developer_token=developer_token,
            start_date=effective_start,
            end_date=effective_end,
            login_customer_id=login_customer_id,
        )
        all_metrics.extend(
            replace(
                metric,
                account_external_id=account.external_id,
                account_name=metric.account_name or account.name,
            )
            for metric in metrics
        )

    analysis = analyze_campaign_import(
        db,
        _metrics_csv(all_metrics),
        SOURCE,
        "",
        "Google Ads API",
        None,
    )
    if analysis["error_count"]:
        raise GoogleAdsApiError("Google Ads API rows không qua kiểm tra import an toàn")
    reconciliation = {
        "matched_rows": analysis["duplicates_existing"],
        "different_rows": analysis["update_rows"],
        "new_rows": analysis["new_rows"],
        "mapped_rows": analysis["mapped_rows"],
        "unmapped_rows": analysis["unmapped_rows"],
    }
    written = 0
    if commit:
        written = commit_campaign_import(
            db,
            analysis,
            actor="auto-google-ads-api",
            connector=CONNECTOR,
            link_source="GOOGLE_ADS_API",
            sync_metadata={
                "api_version": API_VERSION,
                "date_from": effective_start.isoformat(),
                "date_to": effective_end.isoformat(),
                "reconciliation_before_commit": reconciliation,
                "write_operations_enabled": False,
                "csv_fallback_enabled": True,
            },
        )
    return {
        "status": "SUCCESS" if commit else "PREVIEW",
        "mode": "READ_ONLY_REPORTING",
        "api_version": API_VERSION,
        "date_from": effective_start.isoformat(),
        "date_to": effective_end.isoformat(),
        "customer_count": len(accounts),
        "rows_read": analysis["rows_read"],
        "rows_written": written,
        "auto_mapped_rows": analysis["auto_mapped_rows"],
        "reconciliation_before_commit": reconciliation,
        "totals_by_currency": analysis["totals_by_currency"],
        "write_operations_enabled": False,
        "csv_fallback_enabled": True,
    }


def sync_google_ads_api(
    db: Session,
    *,
    now: datetime | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    commit: bool = True,
    credential_checker: Callable[[str], bool] = credential_present,
    credential_reader: Callable[[str], str] = read_credential,
    token_refresher: Callable = refresh_access_token,
    metrics_searcher: Callable = search_campaign_metrics,
) -> dict:
    started_at = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    try:
        return _sync_google_ads_api(
            db,
            now=started_at,
            start_date=start_date,
            end_date=end_date,
            commit=commit,
            credential_checker=credential_checker,
            credential_reader=credential_reader,
            token_refresher=token_refresher,
            metrics_searcher=metrics_searcher,
        )
    except Exception as exc:
        if not commit:
            raise
        db.rollback()
        sanitized = (
            exc
            if isinstance(exc, GoogleAdsApiError)
            else GoogleAdsApiError("Google Ads API sync thất bại")
        )
        try:
            sync_status = SyncStatus(sanitized.category)
        except ValueError:
            sync_status = SyncStatus.ERROR
        effective_end = end_date or (started_at.date() - timedelta(days=1))
        effective_start = start_date or (
            effective_end - timedelta(days=LOOKBACK_DAYS - 1)
        )
        db.add(
            SyncRun(
                connector=CONNECTOR,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                status=sync_status,
                rows_read=0,
                rows_written=0,
                error_summary=str(sanitized),
                metadata_json={
                    "api_version": API_VERSION,
                    "date_from": effective_start.isoformat(),
                    "date_to": effective_end.isoformat(),
                    "failure_category": sync_status.value,
                    "requires_user": sync_status == SyncStatus.AUTH_FAILED,
                    "max_retry_attempts": 3,
                    "write_operations_enabled": False,
                    "csv_fallback_enabled": True,
                },
            )
        )
        db.commit()
        if sanitized is exc:
            raise
        raise sanitized from exc
