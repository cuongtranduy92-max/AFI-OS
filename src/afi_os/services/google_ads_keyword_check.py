from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, DataQuality
from afi_os.models import AdsAccount, AuditLog, MetricSnapshot, Project
from afi_os.services.google_ads_api import (
    GoogleAdsApiError,
    GoogleAdsKeywordMetric,
    generate_domain_keyword_ideas,
    refresh_access_token,
)
from afi_os.services.google_ads_keychain import credential_present, read_credential
from afi_os.services.google_ads_readiness import google_ads_readiness

KEYWORD_IDEAS_DOCS_URL = (
    "https://developers.google.com/google-ads/api/docs/keyword-planning/generate-keyword-ideas"
)
KEYWORD_VALID_DAYS = 7


def cached_keyword_result(
    db: Session,
    project: Project,
    *,
    now: datetime | None = None,
) -> dict | None:
    """Return keyword metrics only when all three canonical snapshots are fresh."""

    now = now or datetime.now(UTC)
    keys = {
        "primary_keyword_search_volume",
        "primary_keyword_bid_low",
        "primary_keyword_bid_high",
    }
    snapshots = list(
        db.scalars(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.project_id == project.id,
                MetricSnapshot.metric_key.in_(keys),
            )
            .order_by(MetricSnapshot.observed_at.desc(), MetricSnapshot.id.desc())
        ).all()
    )
    latest: dict[str, MetricSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.metric_key in latest or snapshot.valid_until is None:
            continue
        valid_until = snapshot.valid_until
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until >= now:
            latest[snapshot.metric_key] = snapshot
    if set(latest) != keys:
        return None
    observed_at = min(item.observed_at for item in latest.values())
    return {
        "status": "CACHED",
        "detail": "Đang dùng từ khóa và CPC còn hạn trong cache 7 ngày.",
        "requires_user": False,
        "fields": sorted(keys),
        "source_urls": sorted(
            {item.source_url for item in latest.values() if item.source_url}
        ),
        "cache_hit": True,
        "checked_at": observed_at,
    }


def _normalized(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _select_primary(
    ideas: list[GoogleAdsKeywordMetric],
    project: Project,
) -> GoogleAdsKeywordMetric:
    candidates = {
        _normalized(project.brand_name),
        _normalized(project.domain.split(".", 1)[0]),
        _normalized(project.domain),
    }
    exact = [item for item in ideas if _normalized(item.text) in candidates]
    return max(exact or ideas, key=lambda item: item.average_monthly_searches)


def _snapshot(
    db: Session,
    project: Project,
    *,
    metric_key: str,
    value: Decimal,
    unit: str,
    currency: str,
    primary: GoogleAdsKeywordMetric,
    ideas: list[GoogleAdsKeywordMetric],
    source_url: str,
    now: datetime,
) -> tuple[MetricSnapshot, bool]:
    period = now.date().replace(day=1)
    canonical = json.dumps(
        {
            "project_id": project.id,
            "metric_key": metric_key,
            "period": period.isoformat(),
            "keyword": primary.text,
            "value": str(value.normalize()),
            "currency": currency,
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
            metric_key=metric_key,
            numeric_value=value,
            unit=unit,
            quality=DataQuality.OBSERVED,
            source_name="Google Ads Keyword Planner API",
            source_url=source_url,
            observed_at=now,
            valid_until=now + timedelta(days=KEYWORD_VALID_DAYS),
            confidence=0.95,
            geography="GLOBAL",
            language="en",
            date_from=period,
            date_to=period,
            method_version="google-keyword-planner-domain-v1",
            source_hash=source_hash,
            payload_json={
                "entry_type": "AUTO_API",
                "primary_keyword": primary.text,
                "top_related_keywords": [
                    {
                        "text": item.text,
                        "average_monthly_searches": item.average_monthly_searches,
                    }
                    for item in sorted(
                        ideas,
                        key=lambda idea: idea.average_monthly_searches,
                        reverse=True,
                    )[:20]
                ],
                "credentials_stored": False,
                "write_operations_enabled": False,
            },
        )
        db.add(snapshot)
        db.flush()
    return snapshot, created


def collect_project_keyword_metrics(
    db: Session,
    project: Project,
    *,
    now: datetime | None = None,
    readiness_getter: Callable = google_ads_readiness,
    credential_checker: Callable[[str], bool] = credential_present,
    credential_reader: Callable[[str], str] = read_credential,
    token_refresher: Callable = refresh_access_token,
    idea_generator: Callable = generate_domain_keyword_ideas,
    force_refresh: bool = False,
) -> dict:
    now = now or datetime.now(UTC)
    cached = cached_keyword_result(db, project, now=now)
    if cached is not None and not force_refresh:
        return cached
    readiness = readiness_getter(db, credential_checker=credential_checker)
    if readiness.get("status") != "READY":
        return {
            "status": "CONNECTION_REQUIRED",
            "detail": "Google Ads API chưa sẵn sàng cho Keyword Planner.",
            "requires_user": True,
            "fields": [
                "primary_keyword_search_volume",
                "primary_keyword_bid_low",
                "primary_keyword_bid_high",
            ],
            "source_urls": [KEYWORD_IDEAS_DOCS_URL],
        }
    customer_ids = list(readiness.get("customer_ids", []))
    if not customer_ids:
        return {
            "status": "CONNECTION_REQUIRED",
            "detail": "Google Ads chưa có Customer ID để chạy Keyword Planner.",
            "requires_user": True,
            "fields": [
                "primary_keyword_search_volume",
                "primary_keyword_bid_low",
                "primary_keyword_bid_high",
            ],
            "source_urls": [KEYWORD_IDEAS_DOCS_URL],
        }
    account = next(
        (
            candidate
            for candidate in db.scalars(select(AdsAccount).order_by(AdsAccount.id.asc())).all()
            if "".join(character for character in candidate.external_id if character.isdigit())
            == customer_ids[0]
        ),
        None,
    )
    if account is None:
        return {
            "status": "CONNECTION_REQUIRED",
            "detail": "Customer ID Google Ads trong database chưa nhất quán.",
            "requires_user": True,
            "fields": [
                "primary_keyword_search_volume",
                "primary_keyword_bid_low",
                "primary_keyword_bid_high",
            ],
            "source_urls": [KEYWORD_IDEAS_DOCS_URL],
        }
    try:
        access_token = token_refresher(
            client_id=credential_reader("oauth-client-id"),
            client_secret=credential_reader("oauth-client-secret"),
            refresh_token=credential_reader("refresh-token"),
        )
        login_customer_id = (
            credential_reader("login-customer-id")
            if credential_checker("login-customer-id")
            else None
        )
        ideas = idea_generator(
            customer_id=customer_ids[0],
            domain=project.domain,
            brand_name=project.brand_name,
            access_token=access_token,
            developer_token=credential_reader("developer-token"),
            login_customer_id=login_customer_id,
        )
        primary = _select_primary(ideas, project)
        source_url = (
            f"https://googleads.googleapis.com/v25/customers/{customer_ids[0]}:generateKeywordIdeas"
        )
        entries = (
            (
                "primary_keyword_search_volume",
                Decimal(primary.average_monthly_searches),
                "searches/month",
            ),
            ("primary_keyword_bid_low", primary.bid_low, f"{account.currency}/click"),
            ("primary_keyword_bid_high", primary.bid_high, f"{account.currency}/click"),
        )
        snapshots = [
            _snapshot(
                db,
                project,
                metric_key=key,
                value=value,
                unit=unit,
                currency=account.currency,
                primary=primary,
                ideas=ideas,
                source_url=source_url,
                now=now,
            )
            for key, value, unit in entries
        ]
        for snapshot, _created in snapshots:
            snapshot.observed_at = now
            snapshot.valid_until = now + timedelta(days=KEYWORD_VALID_DAYS)
        db.add(
            AuditLog(
                entity_type="project_keyword_check",
                entity_id=str(project.id),
                action=AuditAction.IMPORT,
                actor="google-keyword-planner-domain-v1",
                payload_json={
                    "domain": project.domain,
                    "primary_keyword": primary.text,
                    "idea_count": len(ideas),
                    "snapshot_ids": [snapshot.id for snapshot, _created in snapshots],
                    "credentials_stored": False,
                    "permissions_changed": False,
                    "campaign_state_changed": False,
                    "google_ads_write": False,
                },
            )
        )
        db.commit()
    except (GoogleAdsApiError, RuntimeError) as exc:
        detail = str(exc)
        return {
            "status": "ACCESS_REQUIRED",
            "detail": (
                f"{detail}. Nếu campaign reporting vẫn chạy, hãy xin Google Ads "
                "Basic Access + quyền nghiên cứu từ khóa."
            ),
            "requires_user": True,
            "fields": [
                "primary_keyword_search_volume",
                "primary_keyword_bid_low",
                "primary_keyword_bid_high",
            ],
            "source_urls": [KEYWORD_IDEAS_DOCS_URL],
        }
    return {
        "status": "COLLECTED",
        "detail": (
            f"Đã lấy từ khóa chính “{primary.text}”, search volume và CPC tiếng Anh/toàn cầu."
        ),
        "requires_user": False,
        "fields": [
            "primary_keyword_search_volume",
            "primary_keyword_bid_low",
            "primary_keyword_bid_high",
        ],
        "source_urls": [source_url, KEYWORD_IDEAS_DOCS_URL],
    }
