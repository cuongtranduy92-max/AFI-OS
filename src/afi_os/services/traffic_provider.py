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
APIFY_ACTOR_ID = "BBX2Pjax6ghxvPBqV"  # trakk/similarweb-scraper
APIFY_SYNC_URL = (
    "https://api.apify.com/v2/acts/" + APIFY_ACTOR_ID + "/run-sync-get-dataset-items"
)
APIFY_SOURCE_URL = "https://apify.com/trakk/similarweb-scraper"
APIFY_TIMEOUT_S = 120.0
APIFY_BATCH_SIZE = 50
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


@dataclass(frozen=True)
class TrafficObservationEx(TrafficObservation):
    """Traffic observation with top country shares in the 0..1 range."""

    top_countries: tuple[tuple[str, float], ...] = ()


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


def _latest_month_visits(estimated: dict | None) -> tuple[Decimal, date] | None:
    """Return the latest valid month from an Apify estimatedMonthlyVisits object."""

    if not isinstance(estimated, dict) or not estimated:
        return None
    for month_key in sorted((str(key) for key in estimated), reverse=True):
        try:
            period = date.fromisoformat(month_key)
        except ValueError:
            continue
        visits = _positive_decimal(estimated.get(month_key))
        if visits is not None:
            return visits, period.replace(day=1)
    return None


def _apify_item_observation(
    domain: str,
    item: dict,
    *,
    now: datetime,
) -> TrafficObservationEx:
    parsed = _latest_month_visits(item.get("estimatedMonthlyVisits"))
    if parsed is None:
        visits = _positive_decimal(item.get("visits"))
        if visits is None:
            raise TrafficProviderError("NO_DATA", f"Thiếu monthly visits cho {domain}")
        parsed = (visits, _previous_month(now))
    monthly_visits, period = parsed

    countries: list[tuple[str, float]] = []
    for entry in item.get("topCountryShares") or []:
        if not isinstance(entry, dict):
            continue
        code = entry.get("countryCode")
        share = entry.get("share")
        if code and isinstance(share, (int, float)) and 0 < share <= 1:
            countries.append((str(code).upper(), float(share)))
    countries.sort(key=lambda pair: pair[1], reverse=True)

    return TrafficObservationEx(
        provider="APIFY_SIMILARWEB",
        monthly_visits=monthly_visits,
        period=period,
        source_url=f"{APIFY_SOURCE_URL}#{domain}",
        confidence=0.75,
        top_countries=tuple(countries[:5]),
    )


def fetch_apify_similarweb(
    domain: str,
    api_token: str,
    *,
    now: datetime,
    transport: Callable[..., httpx.Response] | None = None,
) -> TrafficObservationEx:
    """Call the synchronous Apify Similarweb actor for exactly one domain."""

    payload = {"domains": [domain], "mode": "base_data", "maxConcurrency": 1}
    post = transport or httpx.post
    try:
        response = post(
            APIFY_SYNC_URL,
            params={"token": api_token},
            json=payload,
            timeout=APIFY_TIMEOUT_S,
        )
    except httpx.RequestError as exc:
        raise TrafficProviderError("ERROR", "Không kết nối được Apify") from exc
    _http_error(response)
    try:
        items = response.json()
    except ValueError as exc:
        raise TrafficProviderError("ERROR", "Apify trả dữ liệu không hợp lệ") from exc
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise TrafficProviderError("NO_DATA", f"Apify không trả dữ liệu cho {domain}")
    return _apify_item_observation(domain, items[0], now=now)


def _item_domain(item: dict) -> str | None:
    raw = item.get("domain") or item.get("site") or item.get("url")
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = raw.strip().lower()
    normalized = normalized.removeprefix("https://").removeprefix("http://")
    normalized = normalized.removeprefix("www.").split("/", 1)[0]
    return normalized or None


def fetch_apify_similarweb_batch(
    domains: list[str],
    api_token: str,
    *,
    now: datetime,
    transport: Callable[..., httpx.Response] | None = None,
) -> dict[str, TrafficObservationEx | TrafficProviderError]:
    """Fetch up to 50 domains in one paid actor run and retain per-domain failures."""

    if not domains or len(domains) > APIFY_BATCH_SIZE:
        raise ValueError(f"Apify batch phải có 1–{APIFY_BATCH_SIZE} domain")
    payload = {
        "domains": domains,
        "mode": "base_data",
        "maxConcurrency": min(10, len(domains)),
    }
    post = transport or httpx.post
    try:
        response = post(
            APIFY_SYNC_URL,
            params={"token": api_token},
            json=payload,
            timeout=APIFY_TIMEOUT_S,
        )
    except httpx.RequestError as exc:
        raise TrafficProviderError("ERROR", "Không kết nối được Apify") from exc
    _http_error(response)
    try:
        items = response.json()
    except ValueError as exc:
        raise TrafficProviderError("ERROR", "Apify trả dữ liệu không hợp lệ") from exc
    if not isinstance(items, list):
        raise TrafficProviderError("ERROR", "Apify batch không trả danh sách dữ liệu")

    item_by_domain = {
        item_domain: item
        for item in items
        if isinstance(item, dict) and (item_domain := _item_domain(item))
    }
    if not item_by_domain and len(items) == len(domains):
        item_by_domain = {
            domain: item
            for domain, item in zip(domains, items, strict=True)
            if isinstance(item, dict)
        }

    results: dict[str, TrafficObservationEx | TrafficProviderError] = {}
    for domain in domains:
        item = item_by_domain.get(domain)
        if item is None:
            results[domain] = TrafficProviderError(
                "NO_DATA", f"Apify không trả dữ liệu cho {domain}"
            )
            continue
        try:
            results[domain] = _apify_item_observation(domain, item, now=now)
        except TrafficProviderError as exc:
            results[domain] = exc
    return results


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
    traffic_created = snapshot is None
    if snapshot is None:
        snapshot = MetricSnapshot(
            project_id=project.id,
            metric_key="website_traffic_monthly",
            numeric_value=observation.monthly_visits,
            unit="visits/month",
            quality=DataQuality.ESTIMATED,
            source_name=f"{observation.provider.replace('_', ' ').title()} API",
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
    countries_created = False
    countries = getattr(observation, "top_countries", ())
    if countries:
        countries_value = [[code, share] for code, share in countries]
        countries_canonical = json.dumps(
            {
                "project_id": project.id,
                "metric_key": "top_traffic_countries",
                "provider": observation.provider,
                "period": observation.period.isoformat(),
                "value": countries_value,
                "geography": "GLOBAL",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        countries_hash = hashlib.sha256(countries_canonical.encode()).hexdigest()
        countries_snapshot = db.scalar(
            select(MetricSnapshot).where(MetricSnapshot.source_hash == countries_hash)
        )
        if countries_snapshot is None:
            countries_snapshot = MetricSnapshot(
                project_id=project.id,
                metric_key="top_traffic_countries",
                text_value=json.dumps(countries_value, separators=(",", ":")),
                unit="traffic share",
                quality=DataQuality.ESTIMATED,
                source_name=f"{observation.provider.replace('_', ' ').title()} API",
                source_url=observation.source_url,
                observed_at=now,
                valid_until=now + timedelta(days=TRAFFIC_VALID_DAYS),
                confidence=observation.confidence,
                geography="GLOBAL",
                date_from=observation.period,
                date_to=period_end,
                method_version="traffic-provider-api-v2",
                source_hash=countries_hash,
                payload_json={
                    "entry_type": "AUTO_API",
                    "provider": observation.provider,
                    "period": observation.period.isoformat(),
                    "secret_stored": False,
                },
            )
            db.add(countries_snapshot)
            db.flush()
            countries_created = True
            db.add(
                AuditLog(
                    entity_type="project_metric_snapshot",
                    entity_id=str(countries_snapshot.id),
                    action=AuditAction.IMPORT,
                    actor=actor,
                    payload_json={
                        "project_id": project.id,
                        "metric_key": countries_snapshot.metric_key,
                        "provider": observation.provider,
                        "source_url": observation.source_url,
                        "period": observation.period.isoformat(),
                        "confidence": observation.confidence,
                        "country_count": len(countries),
                        "api_key_stored": False,
                        "permissions_changed": False,
                        "campaign_state_changed": False,
                        "google_ads_write": False,
                    },
                )
            )
    db.commit()
    return snapshot, traffic_created or countries_created


def _fresh_snapshot(
    db: Session,
    project_id: int,
    metric_key: str,
    *,
    now: datetime,
) -> MetricSnapshot | None:
    candidates = list(
        db.scalars(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.project_id == project_id,
                MetricSnapshot.metric_key == metric_key,
            )
            .order_by(MetricSnapshot.observed_at.desc(), MetricSnapshot.id.desc())
        ).all()
    )
    for snapshot in candidates:
        valid_until = snapshot.valid_until
        if valid_until is None:
            continue
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until >= now:
            return snapshot
    return None


def _cached_traffic_result(db: Session, project: Project, *, now: datetime) -> dict | None:
    traffic = _fresh_snapshot(db, project.id, "website_traffic_monthly", now=now)
    countries = _fresh_snapshot(db, project.id, "top_traffic_countries", now=now)
    if traffic is None:
        return None
    fields = ["website_traffic_monthly"]
    if countries is not None:
        fields.append("top_traffic_countries")
    return {
        "status": "CACHED",
        "provider": (traffic.payload_json or {}).get("provider"),
        "fields": fields,
        "detail": (
            "Đang dùng traffic và top quốc gia còn hạn trong cache 45 ngày."
            if countries is not None
            else "Đang dùng traffic còn hạn trong cache 45 ngày; chưa có top quốc gia."
        ),
        "requires_user": False,
        "source_urls": [traffic.source_url] if traffic.source_url else [],
        "snapshot_id": traffic.id,
        "created": False,
        "cache_hit": True,
        "google_ads_write": False,
    }


def _provider_source_urls(provider: str) -> list[str]:
    if provider == "SIMILARWEB":
        return [SIMILARWEB_DOCS_URL]
    if provider == "SEMRUSH":
        return [SEMRUSH_DOCS_URL]
    return [APIFY_SOURCE_URL]


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
    cached = _cached_traffic_result(db, project, now=now)
    apify_needs_countries = (
        readiness.get("status") == "READY"
        and str(readiness.get("provider", "")).upper() == "APIFY"
        and cached is not None
        and "top_traffic_countries" not in cached["fields"]
    )
    if cached is not None and not apify_needs_countries:
        return cached
    if readiness.get("status") != "READY":
        return {
            **readiness,
            "status": "CONNECTION_REQUIRED",
            "fields": ["website_traffic_monthly", "top_traffic_countries"],
            "detail": (
                "Kết nối Apify, Similarweb API hoặc Semrush Trends API một lần; "
                "sau đó mỗi lần chỉ nhập domain."
            ),
            "requires_user": True,
            "source_urls": [APIFY_SOURCE_URL, SIMILARWEB_DOCS_URL, SEMRUSH_DOCS_URL],
            "google_ads_write": False,
        }
    provider = str(readiness["provider"]).upper()
    fetchers = fetchers or {
        "SIMILARWEB": fetch_similarweb,
        "SEMRUSH": fetch_semrush,
        "APIFY": fetch_apify_similarweb,
    }
    try:
        observation = fetchers[provider](project.domain, credential_reader("api-key"), now=now)
        snapshot, created = store_traffic_observation(db, project, observation, now=now)
    except (TrafficProviderError, RuntimeError) as exc:
        if isinstance(exc, TrafficProviderError):
            status, detail = exc.status, exc.detail
        else:
            status, detail = "AUTH_FAILED", "Không đọc được token traffic trong Keychain"
        return {
            **readiness,
            "status": status,
            "fields": ["website_traffic_monthly", "top_traffic_countries"],
            "detail": detail,
            "requires_user": status == "AUTH_FAILED",
            "source_urls": _provider_source_urls(provider),
            "google_ads_write": False,
        }
    return {
        **readiness,
        "status": "COLLECTED",
        "fields": [
            "website_traffic_monthly",
            *(["top_traffic_countries"] if getattr(observation, "top_countries", ()) else []),
        ],
        "detail": f"Đã lấy traffic tháng {observation.period.strftime('%Y-%m')}.",
        "requires_user": False,
        "source_urls": [observation.source_url],
        "snapshot_id": snapshot.id,
        "created": created,
        "google_ads_write": False,
    }


def collect_project_traffic_batch(
    db: Session,
    projects: list[Project],
    *,
    now: datetime | None = None,
    readiness_getter: Callable[[], dict] = traffic_provider_readiness,
    credential_reader: Callable[[str], str] = read_credential,
    batch_fetcher: Callable = fetch_apify_similarweb_batch,
) -> dict[str, dict]:
    """Pre-collect uncached Apify traffic in one actor call for an appraisal batch."""

    now = now or datetime.now(UTC)
    readiness = readiness_getter()
    results: dict[str, dict] = {}
    uncached: list[Project] = []
    for project in projects:
        cached = _cached_traffic_result(db, project, now=now)
        apify_needs_countries = (
            readiness.get("status") == "READY"
            and str(readiness.get("provider", "")).upper() == "APIFY"
            and cached is not None
            and "top_traffic_countries" not in cached["fields"]
        )
        if cached is not None and not apify_needs_countries:
            results[project.domain] = cached
        else:
            uncached.append(project)
    if not uncached:
        return results

    if readiness.get("status") != "READY" or str(readiness.get("provider", "")).upper() != "APIFY":
        return results
    domains = [project.domain for project in uncached]
    try:
        observations = batch_fetcher(domains, credential_reader("api-key"), now=now)
    except (TrafficProviderError, RuntimeError) as exc:
        if isinstance(exc, TrafficProviderError):
            status, detail = exc.status, exc.detail
        else:
            status, detail = "AUTH_FAILED", "Không đọc được token Apify trong Keychain"
        for project in uncached:
            results[project.domain] = {
                **readiness,
                "status": status,
                "fields": ["website_traffic_monthly", "top_traffic_countries"],
                "detail": detail,
                "requires_user": status == "AUTH_FAILED",
                "source_urls": [APIFY_SOURCE_URL],
                "google_ads_write": False,
            }
        return results

    for project in uncached:
        observation = observations.get(project.domain)
        if isinstance(observation, TrafficProviderError) or observation is None:
            error = observation or TrafficProviderError(
                "NO_DATA", f"Apify không trả dữ liệu cho {project.domain}"
            )
            results[project.domain] = {
                **readiness,
                "status": error.status,
                "fields": ["website_traffic_monthly", "top_traffic_countries"],
                "detail": error.detail,
                "requires_user": error.status == "AUTH_FAILED",
                "source_urls": [APIFY_SOURCE_URL],
                "google_ads_write": False,
            }
            continue
        snapshot, created = store_traffic_observation(db, project, observation, now=now)
        results[project.domain] = {
            **readiness,
            "status": "COLLECTED",
            "fields": ["website_traffic_monthly", "top_traffic_countries"],
            "detail": f"Đã lấy traffic tháng {observation.period.strftime('%Y-%m')} theo batch.",
            "requires_user": False,
            "source_urls": [observation.source_url],
            "snapshot_id": snapshot.id,
            "created": created,
            "cache_hit": False,
            "google_ads_write": False,
        }
    return results
