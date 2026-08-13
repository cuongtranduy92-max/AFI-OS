from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from afi_os.config import (
    ADVERTISER_ACTIVE_DAYS,
    ADVERTISER_CACHE_DAYS,
    ADVERTISER_GOLDMINE_MIN,
    ADVERTISER_MONTHLY_QUOTA,
    ADVERTISER_PROVIDER,
)
from afi_os.enums import CaptureStatus, DataQuality
from afi_os.models import (
    AdObservation,
    Advertiser,
    AdvertiserApiUsage,
    MetricSnapshot,
    Project,
    RawCapture,
)
from afi_os.services.advertiser_keychain import (
    advertiser_provider_readiness,
    read_credential,
)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
SERPAPI_PUBLIC_SOURCE = "https://adstransparency.google.com/"
DOMAIN_CACHE_KIND = "SERPAPI_DOMAIN_ADVERTISERS_V1"
EXPANSION_CACHE_KIND = "SERPAPI_ADVERTISER_DOMAINS_V1"


class AdvertiserProviderError(RuntimeError):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class AdvertiserCreative:
    advertiser_id: str
    advertiser_name: str
    creative_id: str
    ad_format: str | None
    target_domain: str | None
    first_shown: datetime | None
    last_shown: datetime | None
    details_link: str


@dataclass(frozen=True)
class AdvertiserPage:
    creatives: tuple[AdvertiserCreative, ...]
    next_page_token: str | None = None


def _utc_timestamp(value: Any) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _domain(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().lower()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").rstrip(".").removeprefix("www.")
    return host if "." in host else None


def _parse_page(payload: dict[str, Any]) -> AdvertiserPage:
    if payload.get("error"):
        detail = str(payload["error"])
        lower = detail.lower()
        status = "AUTH_FAILED" if "api key" in lower or "account" in lower else "RETRY_REQUIRED"
        if "limit" in lower or "quota" in lower or "searches" in lower:
            status = "RATE_LIMITED"
        raise AdvertiserProviderError(status, detail)
    creatives: list[AdvertiserCreative] = []
    for item in payload.get("ad_creatives") or []:
        advertiser_id = str(item.get("advertiser_id") or "").strip()
        advertiser_name = str(item.get("advertiser") or "").strip()
        creative_id = str(item.get("ad_creative_id") or "").strip()
        if not advertiser_id or not advertiser_name or not creative_id:
            continue
        details_link = str(
            item.get("details_link")
            or f"https://adstransparency.google.com/advertiser/{advertiser_id}"
        )
        creatives.append(
            AdvertiserCreative(
                advertiser_id=advertiser_id,
                advertiser_name=advertiser_name,
                creative_id=creative_id,
                ad_format=(str(item["format"]).strip() if item.get("format") else None),
                target_domain=_domain(item.get("target_domain")),
                first_shown=_utc_timestamp(item.get("first_shown")),
                last_shown=_utc_timestamp(item.get("last_shown")),
                details_link=details_link,
            )
        )
    pagination = payload.get("serpapi_pagination") or {}
    return AdvertiserPage(
        creatives=tuple(creatives),
        next_page_token=(
            str(pagination["next_page_token"])
            if pagination.get("next_page_token")
            else None
        ),
    )


def _request_serpapi(
    params: dict[str, Any],
    api_key: str,
    *,
    transport: Callable[..., httpx.Response] = httpx.get,
) -> AdvertiserPage:
    safe_params = {
        "engine": "google_ads_transparency_center",
        "num": 100,
        **params,
        "api_key": api_key,
    }
    try:
        response = transport(SERPAPI_ENDPOINT, params=safe_params, timeout=15.0)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise AdvertiserProviderError(
            "RETRY_REQUIRED", "SerpApi tạm thời không phản hồi"
        ) from exc
    if response.status_code in {401, 403}:
        raise AdvertiserProviderError("AUTH_FAILED", "SerpApi từ chối API key")
    if response.status_code == 429:
        raise AdvertiserProviderError("RATE_LIMITED", "SerpApi báo hết hạn mức")
    if response.status_code >= 500:
        raise AdvertiserProviderError("RETRY_REQUIRED", "SerpApi đang gặp lỗi tạm thời")
    if response.status_code >= 400:
        raise AdvertiserProviderError(
            "ERROR", f"SerpApi trả HTTP {response.status_code}"
        )
    try:
        return _parse_page(response.json())
    except ValueError as exc:
        raise AdvertiserProviderError("ERROR", "SerpApi trả dữ liệu không hợp lệ") from exc


def fetch_advertisers_by_domain(
    domain: str,
    api_key: str,
    *,
    transport: Callable[..., httpx.Response] = httpx.get,
) -> AdvertiserPage:
    if ADVERTISER_PROVIDER != "SERPAPI":
        raise AdvertiserProviderError(
            "CONNECTION_REQUIRED",
            f"Chưa cài adapter advertiser cho provider {ADVERTISER_PROVIDER}",
        )
    return _request_serpapi({"text": domain}, api_key, transport=transport)


def fetch_domains_by_advertiser(
    advertiser_ids: Sequence[str],
    api_key: str,
    *,
    next_page_token: str | None = None,
    transport: Callable[..., httpx.Response] = httpx.get,
) -> AdvertiserPage:
    ids = [item.strip() for item in advertiser_ids if item.strip()]
    if not ids or len(ids) > 5:
        raise ValueError("Mỗi lượt chỉ được mở rộng từ 1 đến 5 advertiser")
    if ADVERTISER_PROVIDER != "SERPAPI":
        raise AdvertiserProviderError(
            "CONNECTION_REQUIRED",
            f"Chưa cài adapter advertiser cho provider {ADVERTISER_PROVIDER}",
        )
    params: dict[str, Any] = {"advertiser_id": ",".join(ids)}
    if next_page_token:
        params["next_page_token"] = next_page_token
    return _request_serpapi(params, api_key, transport=transport)


def _month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


def monthly_usage(db: Session, *, day: date | None = None) -> int:
    current = day or datetime.now(UTC).date()
    start, end = _month_bounds(current)
    return int(
        db.scalar(
            select(func.coalesce(func.sum(AdvertiserApiUsage.call_count), 0)).where(
                AdvertiserApiUsage.usage_date >= start,
                AdvertiserApiUsage.usage_date < end,
            )
        )
        or 0
    )


def quota_status(db: Session, *, day: date | None = None) -> dict[str, Any]:
    used = monthly_usage(db, day=day)
    ratio = used / ADVERTISER_MONTHLY_QUOTA
    state = "BLOCKED" if used >= ADVERTISER_MONTHLY_QUOTA else (
        "WARNING" if ratio >= 0.8 else "OK"
    )
    return {
        "used": used,
        "limit": ADVERTISER_MONTHLY_QUOTA,
        "remaining": max(0, ADVERTISER_MONTHLY_QUOTA - used),
        "state": state,
        "message": (
            "Hết hạn mức tháng, nâng gói hoặc đợi tháng sau"
            if state == "BLOCKED"
            else f"Đã dùng {used}/{ADVERTISER_MONTHLY_QUOTA} lượt tháng này"
        ),
    }


def _consume_usage(db: Session, endpoint: str, *, now: datetime) -> None:
    status = quota_status(db, day=now.date())
    if status["state"] == "BLOCKED":
        raise AdvertiserProviderError("QUOTA_EXHAUSTED", status["message"])
    db.add(
        AdvertiserApiUsage(usage_date=now.date(), call_count=1, endpoint=endpoint)
    )
    db.commit()


def _cached_capture(
    db: Session,
    *,
    kind: str,
    identity: str,
    now: datetime,
) -> RawCapture | None:
    cutoff = now - timedelta(days=ADVERTISER_CACHE_DAYS)
    candidates = db.scalars(
        select(RawCapture)
        .where(RawCapture.parser_version == kind, RawCapture.captured_at >= cutoff)
        .order_by(RawCapture.captured_at.desc(), RawCapture.id.desc())
    )
    for item in candidates:
        payload = item.parsed_payload or {}
        if payload.get("cache_identity") == identity:
            return item
    return None


def _capture_result(capture: RawCapture) -> dict[str, Any]:
    result = dict((capture.parsed_payload or {}).get("result") or {})
    original_status = str(result.get("status") or "COLLECTED").upper()
    result.update(
        {
            "status": "NO_DATA" if original_status == "NO_DATA" else "CACHED",
            "cache_hit": True,
            "checked_at": capture.captured_at.isoformat(),
            "source_urls": [capture.source_url],
        }
    )
    return result


def cached_project_advertisers(
    db: Session,
    project: Project,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    checked_at = now or datetime.now(UTC)
    capture = _cached_capture(
        db,
        kind=DOMAIN_CACHE_KIND,
        identity=project.domain.lower(),
        now=checked_at,
    )
    return _capture_result(capture) if capture is not None else None


def _store_capture(
    db: Session,
    *,
    kind: str,
    identity: str,
    result: dict[str, Any],
    now: datetime,
) -> RawCapture:
    digest = hashlib.sha256(
        f"{kind}|{identity}|{now.isoformat()}".encode()
    ).hexdigest()
    capture = RawCapture(
        source_url=SERPAPI_PUBLIC_SOURCE,
        page_title=f"SerpApi Ads Transparency · {identity}",
        captured_at=now,
        status=CaptureStatus.PARSED,
        parser_version=kind,
        parsed_payload={
            "cache_identity": identity,
            "provider": "SERPAPI",
            "result": result,
            "api_key_stored": False,
        },
        capture_hash=digest,
    )
    db.add(capture)
    db.flush()
    return capture


def _metric(
    db: Session,
    project: Project,
    key: str,
    value: int,
    *,
    now: datetime,
    detail: str,
) -> None:
    source_hash = hashlib.sha256(
        f"SERPAPI|{project.id}|{key}|{now.isoformat()}|{value}".encode()
    ).hexdigest()
    db.add(
        MetricSnapshot(
            project_id=project.id,
            metric_key=key,
            numeric_value=value,
            unit="advertisers",
            quality=DataQuality.IMPORTED,
            source_name="SerpApi Google Ads Transparency Center",
            source_url=SERPAPI_PUBLIC_SOURCE,
            observed_at=now,
            valid_until=now + timedelta(days=ADVERTISER_CACHE_DAYS),
            confidence=0.85,
            geography="GLOBAL",
            method_version="serpapi-advertiser-v1",
            source_hash=source_hash,
            payload_json={
                "provider": "SERPAPI",
                "change_reason": detail,
                "activity_window_days": ADVERTISER_ACTIVE_DAYS,
            },
        )
    )


def _materialize_creatives(
    db: Session,
    project: Project,
    creatives: Sequence[AdvertiserCreative],
    *,
    now: datetime,
    result_set_complete: bool,
) -> list[Advertiser]:
    advertisers: dict[str, Advertiser] = {}
    counts = Counter(item.advertiser_id for item in creatives)
    for creative in creatives:
        advertiser = advertisers.get(creative.advertiser_id)
        if advertiser is None:
            advertiser = db.scalar(
                select(Advertiser).where(
                    Advertiser.external_key == creative.advertiser_id
                )
            )
        if advertiser is None:
            advertiser = Advertiser(
                external_key=creative.advertiser_id,
                verified_name=creative.advertiser_name,
                confidence=0.85,
                source_url=f"https://adstransparency.google.com/advertiser/{creative.advertiser_id}",
                first_seen_at=creative.first_shown,
                last_seen_at=creative.last_shown,
            )
            db.add(advertiser)
            db.flush()
        else:
            advertiser.verified_name = creative.advertiser_name
            advertiser.confidence = max(advertiser.confidence, 0.85)
            stored_first = (
                advertiser.first_seen_at.replace(tzinfo=UTC)
                if advertiser.first_seen_at and advertiser.first_seen_at.tzinfo is None
                else advertiser.first_seen_at
            )
            stored_last = (
                advertiser.last_seen_at.replace(tzinfo=UTC)
                if advertiser.last_seen_at and advertiser.last_seen_at.tzinfo is None
                else advertiser.last_seen_at
            )
            if creative.first_shown and (
                advertiser.first_seen_at is None
                or creative.first_shown < stored_first
            ):
                advertiser.first_seen_at = creative.first_shown
            if creative.last_shown and (
                advertiser.last_seen_at is None
                or creative.last_shown > stored_last
            ):
                advertiser.last_seen_at = creative.last_shown
        advertisers[creative.advertiser_id] = advertiser
        content_hash = hashlib.sha256(
            f"SERPAPI|{creative.creative_id}|{project.id}".encode()
        ).hexdigest()
        existing = db.scalar(
            select(AdObservation).where(
                AdObservation.advertiser_id == advertiser.id,
                AdObservation.project_id == project.id,
                AdObservation.content_hash == content_hash,
                AdObservation.snapshot_date == now.date(),
            )
        )
        if existing is None:
            db.add(
                AdObservation(
                    advertiser_id=advertiser.id,
                    project_id=project.id,
                    source_url=creative.details_link,
                    ad_format=creative.ad_format,
                    landing_domain=creative.target_domain or project.domain,
                    first_seen_at=creative.first_shown,
                    last_seen_at=creative.last_shown,
                    snapshot_date=now.date(),
                    content_hash=content_hash,
                    metadata_json={
                        "evidence_type": "SERPAPI_AD_CREATIVE",
                        "source_name": "SerpApi Google Ads Transparency Center",
                        "source_authority": "THIRD_PARTY",
                        "checked_at": now.isoformat(),
                        "creative_id": creative.creative_id,
                        "reported_ad_count": counts[creative.advertiser_id],
                        "result_set_complete": result_set_complete,
                        "confidence": 0.85,
                        "activity_window_verified": creative.last_shown is not None,
                    },
                )
            )
    db.flush()
    return list(advertisers.values())


def collect_project_advertisers(
    db: Session,
    project: Project,
    *,
    now: datetime | None = None,
    force_refresh: bool = False,
    readiness_getter: Callable[[], dict] = advertiser_provider_readiness,
    credential_reader: Callable[[], str] = read_credential,
    fetcher: Callable[..., AdvertiserPage] = fetch_advertisers_by_domain,
) -> dict[str, Any]:
    checked_at = now or datetime.now(UTC)
    identity = project.domain.lower()
    cached = _cached_capture(
        db, kind=DOMAIN_CACHE_KIND, identity=identity, now=checked_at
    )
    if cached is not None and not force_refresh:
        return _capture_result(cached)
    readiness = readiness_getter()
    if readiness.get("status") != "READY":
        return {
            "status": "CONNECTION_REQUIRED",
            "detail": "Chưa kết nối SerpApi. Chạy SETUP-ADVERTISER.command một lần.",
            "source_urls": [],
        }
    _consume_usage(db, "DOMAIN_SEARCH", now=checked_at)
    page = fetcher(project.domain, credential_reader())
    advertisers = _materialize_creatives(
        db,
        project,
        page.creatives,
        now=checked_at,
        result_set_complete=not bool(page.next_page_token),
    )
    cutoff = checked_at - timedelta(days=ADVERTISER_ACTIVE_DAYS)
    active = {
        item.advertiser_id
        for item in page.creatives
        if item.last_shown is not None and item.last_shown >= cutoff
    }
    total = {item.advertiser_id for item in page.creatives}
    detail = (
        "Không tìm thấy nhà quảng cáo nào"
        if not total
        else (
            f"Đang chạy {ADVERTISER_ACTIVE_DAYS} ngày: {len(active)} · "
            f"tổng từng thấy: {len(total)}"
            + (" · kết quả đầu 100, nguồn còn phân trang" if page.next_page_token else "")
        )
    )
    _metric(db, project, "active_advertisers_7d", len(active), now=checked_at, detail=detail)
    _metric(db, project, "active_advertisers_30d", len(active), now=checked_at, detail=detail)
    _metric(db, project, "independent_advertisers", len(total), now=checked_at, detail=detail)
    result = {
        "status": "COLLECTED" if total else "NO_DATA",
        "detail": detail,
        "active_count": len(active),
        "total_ever": len(total),
        "advertiser_ids": [item.external_key for item in advertisers],
        "source": "serpapi",
        "cache_hit": False,
        "checked_at": checked_at.isoformat(),
        "source_urls": [SERPAPI_PUBLIC_SOURCE],
        "truncated": bool(page.next_page_token),
    }
    _store_capture(
        db,
        kind=DOMAIN_CACHE_KIND,
        identity=identity,
        result=result,
        now=checked_at,
    )
    db.commit()
    return result


def _expansion_domains(page: AdvertiserPage) -> list[str]:
    return sorted(
        {
            domain
            for item in page.creatives
            if (domain := item.target_domain) is not None
        }
    )


def expand_advertisers(
    db: Session,
    advertiser_ids: Sequence[int],
    *,
    now: datetime | None = None,
    force_refresh: bool = False,
    readiness_getter: Callable[[], dict] = advertiser_provider_readiness,
    credential_reader: Callable[[], str] = read_credential,
    fetcher: Callable[..., AdvertiserPage] = fetch_domains_by_advertiser,
) -> dict[str, Any]:
    ids = list(dict.fromkeys(advertiser_ids))
    if not ids or len(ids) > 5:
        raise ValueError("Mỗi lượt chỉ được mở rộng từ 1 đến 5 advertiser")
    advertisers = list(
        db.scalars(select(Advertiser).where(Advertiser.id.in_(ids))).all()
    )
    if len(advertisers) != len(ids) or any(not item.external_key for item in advertisers):
        raise LookupError("Advertiser chưa có Google advertiser ID")
    checked_at = now or datetime.now(UTC)
    external_ids = sorted(str(item.external_key) for item in advertisers)
    identity = ",".join(external_ids)
    cached = _cached_capture(
        db, kind=EXPANSION_CACHE_KIND, identity=identity, now=checked_at
    )
    previous_domains: set[str] = set()
    previous = db.scalars(
        select(RawCapture)
        .where(RawCapture.parser_version == EXPANSION_CACHE_KIND)
        .order_by(RawCapture.captured_at.desc(), RawCapture.id.desc())
    )
    for item in previous:
        if (item.parsed_payload or {}).get("cache_identity") == identity:
            previous_domains = set(
                ((item.parsed_payload or {}).get("result") or {}).get("domains") or []
            )
            break
    if cached is not None and not force_refresh:
        result = _capture_result(cached)
        result["new_domains"] = []
        return result
    readiness = readiness_getter()
    if readiness.get("status") != "READY":
        raise AdvertiserProviderError(
            "CONNECTION_REQUIRED",
            "Chưa kết nối SerpApi. Chạy SETUP-ADVERTISER.command một lần.",
        )
    token = credential_reader()
    all_creatives: list[AdvertiserCreative] = []
    next_token: str | None = None
    while True:
        _consume_usage(db, "ADVERTISER_EXPANSION", now=checked_at)
        page = fetcher(external_ids, token, next_page_token=next_token)
        all_creatives.extend(page.creatives)
        next_token = page.next_page_token
        if not next_token:
            break
    domains = sorted(
        {
            domain
            for item in all_creatives
            if (domain := item.target_domain) is not None
        }
    )
    new_domains = sorted(set(domains) - previous_domains)
    counts = Counter(item.advertiser_id for item in all_creatives if item.target_domain)
    domains_by_id: dict[str, set[str]] = {}
    for item in all_creatives:
        if item.target_domain:
            domains_by_id.setdefault(item.advertiser_id, set()).add(item.target_domain)
    for advertiser in advertisers:
        found = domains_by_id.get(str(advertiser.external_key), set())
        advertiser.domain_count = len(found)
        advertiser.is_goldmine = advertiser.domain_count >= ADVERTISER_GOLDMINE_MIN
        advertiser.last_expanded_at = checked_at
        stored_last = (
            advertiser.last_seen_at.replace(tzinfo=UTC)
            if advertiser.last_seen_at and advertiser.last_seen_at.tzinfo is None
            else advertiser.last_seen_at
        )
        advertiser.last_seen_at = max(
            (
                item.last_shown
                for item in all_creatives
                if item.advertiser_id == str(advertiser.external_key) and item.last_shown
            ),
            default=stored_last,
        )
    result = {
        "status": "COLLECTED" if domains else "NO_DATA",
        "detail": (
            f"Tìm thấy {len(domains)} domain từ {len(advertisers)} advertiser"
            if domains
            else "Không tìm thấy domain nào cho advertiser này"
        ),
        "domains": domains,
        "new_domains": new_domains,
        "advertisers": [
            {
                "id": item.id,
                "external_key": item.external_key,
                "name": item.verified_name,
                "domain_count": item.domain_count,
                "is_goldmine": item.is_goldmine,
                "reported_ads": counts.get(str(item.external_key), 0),
                "domains": sorted(domains_by_id.get(str(item.external_key), set())),
            }
            for item in advertisers
        ],
        "cache_hit": False,
        "checked_at": checked_at.isoformat(),
        "source_urls": [SERPAPI_PUBLIC_SOURCE],
    }
    _store_capture(
        db,
        kind=EXPANSION_CACHE_KIND,
        identity=identity,
        result=result,
        now=checked_at,
    )
    db.commit()
    return result


def provider_status(db: Session) -> dict[str, Any]:
    return {**advertiser_provider_readiness(), "quota": quota_status(db)}
