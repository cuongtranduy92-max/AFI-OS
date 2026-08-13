from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, DataQuality
from afi_os.models import AuditLog, MetricSnapshot, Project
from afi_os.services.traffic_keychain import read_credential, traffic_provider_readiness

SIMILARWEB_DOCS_URL = "https://developers.similarweb.com/reference/visits"
SEMRUSH_DOCS_URL = "https://developer.semrush.com/api/v3/trends/overview/"
TRAFFIC_VALID_DAYS = 45


class TrafficProviderError(RuntimeError):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class TrafficObservation:
    provider: str
    monthly_visits: Decimal
    period: date
    source_url: str
    confidence: float = 0.8


def _previous_month(now: datetime) -> date:
    first = now.date().replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


def _positive_decimal(value) -> Decimal | None:
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None
    return result if result > 0 else None


def _http_error(response: httpx.Response) -> None:
    if response.status_code in {401, 403}:
        raise TrafficProviderError("AUTH_FAILED", "API key traffic bị từ chối")
    if response.status_code == 429:
        raise TrafficProviderError("RATE_LIMITED", "Provider traffic đã hết hạn mức")
    if response.status_code >= 400:
        raise TrafficProviderError("ERROR", f"Provider traffic trả HTTP {response.status_code}")


def fetch_similarweb(
    domain: str,
    api_key: str,
    *,
    now: datetime,
    transport: Callable[..., httpx.Response] | None = None,
) -> TrafficObservation:
    period = _previous_month(now)
    url = f"https://api.similarweb.com/v1/website/{domain}/total-traffic-and-engagement/visits"
    params = {
        "api_key": api_key,
        "start_date": period.strftime("%Y-%m"),
        "end_date": period.strftime("%Y-%m"),
        "country": "world",
        "granularity": "monthly",
        "main_domain_only": "false",
        "format": "json",
    }
    response = (
        transport(url, params=params)
        if transport is not None
        else httpx.get(url, params=params, timeout=20, follow_redirects=False)
    )
    _http_error(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise TrafficProviderError("ERROR", "Similarweb trả dữ liệu không hợp lệ") from exc
    candidates = payload.get("visits", []) if isinstance(payload, dict) else []
    if isinstance(candidates, dict):
        candidates = [candidates]
    visits = None
    if isinstance(candidates, list):
        for item in reversed(candidates):
            if isinstance(item, dict):
                visits = _positive_decimal(item.get("visits") or item.get("value"))
                if visits is not None:
                    break
    if visits is None and isinstance(payload, dict):
        visits = _positive_decimal(payload.get("visits"))
    if visits is None:
        raise TrafficProviderError("NO_DATA", "Similarweb không trả traffic cho domain này")
    return TrafficObservation("SIMILARWEB", visits, period, url)


def _csv_first_row(text: str) -> dict[str, str]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return next(reader, {}) or {}


def fetch_semrush(
    domain: str,
    api_key: str,
    *,
    now: datetime,
    transport: Callable[..., httpx.Response] | None = None,
) -> TrafficObservation:
    period = _previous_month(now)
    url = "https://api.semrush.com/analytics/ta/api/v3/summary"
    params = {
        "key": api_key,
        "targets": domain,
        "export_columns": "target,visits",
        "display_date": period.isoformat(),
    }
    response = (
        transport(url, params=params)
        if transport is not None
        else httpx.get(url, params=params, timeout=20, follow_redirects=False)
    )
    _http_error(response)
    row = {str(k).strip().lower(): str(v).strip() for k, v in _csv_first_row(response.text).items()}
    visits = _positive_decimal(row.get("visits"))
    if visits is None:
        raise TrafficProviderError("NO_DATA", "Semrush không trả traffic cho domain này")
    source_url = f"{url}?targets={domain}&display_date={period.isoformat()}"
    return TrafficObservation("SEMRUSH", visits, period, source_url)


def store_traffic_observation(
    db: Session,
    project: Project,
    observation: TrafficObservation,
    *,
    now: datetime,
    actor: str = "auto-project-check",
) -> tuple[MetricSnapshot, bool]:
    next_month = (observation.period.replace(day=28) + timedelta(days=4)).replace(day=1)
    period_end = next_month - timedelta(days=1)
    canonical = json.dumps(
        {
            "project_id": project.id,
            "metric_key": "website_traffic_monthly",
            "provider": observation.provider,
            "period": observation.period.isoformat(),
            "value": str(observation.monthly_visits.normalize()),
            "geography": "GLOBAL",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    source_hash = hashlib.sha256(canonical.encode()).hexdigest()
    snapshot = db.scalar(select(MetricSnapshot).where(MetricSnapshot.source_hash == source_hash))
    created = snapshot is None
    if snapshot is None:
        snapshot = MetricSnapshot(
            project_id=project.id,
            metric_key="website_traffic_monthly",
            numeric_value=observation.monthly_visits,
            unit="visits/month",
            quality=DataQuality.ESTIMATED,
            source_name=f"{observation.provider.title()} API",
            source_url=observation.source_url,
            observed_at=now,
            valid_until=now + timedelta(days=TRAFFIC_VALID_DAYS),
            confidence=observation.confidence,
            geography="GLOBAL",
            date_from=observation.period,
            date_to=period_end,
            method_version="traffic-provider-api-v1",
            source_hash=source_hash,
            payload_json={
                "entry_type": "AUTO_API",
                "provider": observation.provider,
                "period": observation.period.isoformat(),
                "secret_stored": False,
            },
        )
        db.add(snapshot)
        db.flush()
        db.add(
            AuditLog(
                entity_type="project_metric_snapshot",
                entity_id=str(snapshot.id),
                action=AuditAction.IMPORT,
                actor=actor,
                payload_json={
                    "project_id": project.id,
                    "metric_key": snapshot.metric_key,
                    "provider": observation.provider,
                    "source_url": observation.source_url,
                    "period": observation.period.isoformat(),
                    "confidence": observation.confidence,
                    "api_key_stored": False,
                    "permissions_changed": False,
                    "campaign_state_changed": False,
                    "google_ads_write": False,
                },
            )
        )
    db.commit()
    return snapshot, created


def collect_project_traffic(
    db: Session,
    project: Project,
    *,
    now: datetime | None = None,
    readiness_getter: Callable[[], dict] = traffic_provider_readiness,
    credential_reader: Callable[[str], str] = read_credential,
    fetchers: dict[str, Callable] | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    readiness = readiness_getter()
    if readiness.get("status") != "READY":
        return {
            **readiness,
            "status": "CONNECTION_REQUIRED",
            "fields": ["website_traffic_monthly", "top_traffic_countries"],
            "detail": (
                "Kết nối Similarweb API hoặc Semrush Trends API một lần; "
                "sau đó mỗi lần chỉ nhập domain."
            ),
            "requires_user": True,
            "source_urls": [SIMILARWEB_DOCS_URL, SEMRUSH_DOCS_URL],
            "google_ads_write": False,
        }
    provider = str(readiness["provider"]).upper()
    fetchers = fetchers or {"SIMILARWEB": fetch_similarweb, "SEMRUSH": fetch_semrush}
    try:
        observation = fetchers[provider](project.domain, credential_reader("api-key"), now=now)
        snapshot, created = store_traffic_observation(db, project, observation, now=now)
    except TrafficProviderError as exc:
        return {
            **readiness,
            "status": exc.status,
            "fields": ["website_traffic_monthly", "top_traffic_countries"],
            "detail": exc.detail,
            "requires_user": exc.status == "AUTH_FAILED",
            "source_urls": [SIMILARWEB_DOCS_URL if provider == "SIMILARWEB" else SEMRUSH_DOCS_URL],
            "google_ads_write": False,
        }
    return {
        **readiness,
        "status": "COLLECTED",
        "fields": ["website_traffic_monthly"],
        "detail": f"Đã lấy traffic tháng {observation.period.strftime('%Y-%m')}.",
        "requires_user": False,
        "source_urls": [observation.source_url],
        "snapshot_id": snapshot.id,
        "created": created,
        "google_ads_write": False,
    }
