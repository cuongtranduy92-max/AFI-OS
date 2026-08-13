from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from afi_os.models import (
    Campaign,
    CampaignChangeEvent,
    CampaignProgramLink,
    CampDiagnosis,
    Click,
    Commission,
    Conversion,
    SyncRun,
)
from afi_os.services.camp_doctor import (
    KW_SHOWING,
    KW_SOMETIMES,
    KW_UNKNOWN,
    CampaignSnapshot,
    ChangeEvent,
    diagnose_campaign,
)
from afi_os.services.google_ads_api import (
    API_VERSION,
    GoogleAdsApiError,
    refresh_access_token,
    search_campaign_detail_reports,
)
from afi_os.services.google_ads_keychain import credential_present, read_credential
from afi_os.services.google_ads_readiness import google_ads_readiness

COMMISSION_FOLDER_CONNECTOR = "AFFILIATE_COMMISSION_FOLDER"
DETAIL_LOOKBACK_DAYS = 30
SUCCESSFUL_COMMISSION_STATES = {"IMPORTED", "UP_TO_DATE"}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _number(value: Any, *, micros: bool = False) -> float | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    if micros:
        parsed /= Decimal("1000000")
    return float(parsed)


def _nested(item: Any, *path: str) -> Any:
    current = item
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _metric_row(row: dict) -> dict:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return {
        "impressions": int(_number(metrics.get("impressions")) or 0),
        "clicks": int(_number(metrics.get("clicks")) or 0),
        "ctr": _number(metrics.get("ctr")),
        "cost": _number(metrics.get("costMicros"), micros=True),
        "conversions_google_ads": _number(metrics.get("conversions")),
    }


def _normalize_details(reports: dict[str, list], *, currency: str) -> dict:
    keywords = []
    for row in reports.get("keywords", []):
        criterion = row.get("adGroupCriterion") or {}
        item = _metric_row(row)
        item.update(
            {
                "keyword": _nested(criterion, "keyword", "text") or "",
                "match_type": _nested(criterion, "keyword", "matchType"),
                "status": criterion.get("status"),
                "average_cpc": _number(_nested(row, "metrics", "averageCpc"), micros=True),
                "search_impression_share": _number(
                    _nested(row, "metrics", "searchImpressionShare")
                ),
                "currency": currency,
            }
        )
        keywords.append(item)

    search_terms = []
    for row in reports.get("search_terms", []):
        item = _metric_row(row)
        view = row.get("searchTermView") or {}
        item.update({"term": view.get("searchTerm") or "", "status": view.get("status")})
        search_terms.append(item)

    devices = []
    for row in reports.get("devices", []):
        item = _metric_row(row)
        item["device"] = _nested(row, "segments", "device") or "Không rõ"
        devices.append(item)

    geography = []
    for row in reports.get("geography", []):
        item = _metric_row(row)
        view = row.get("geographicView") or {}
        item.update(
            {
                "country": (
                    f"Mã quốc gia Google {view.get('countryCriterionId')}"
                    if view.get("countryCriterionId")
                    else "Không rõ"
                ),
                "location_type": view.get("locationType"),
            }
        )
        geography.append(item)

    def demographic(report_name: str, field_name: str, nested_name: str) -> list[dict]:
        output = []
        for row in reports.get(report_name, []):
            item = _metric_row(row)
            item[field_name] = (
                _nested(row, "adGroupCriterion", nested_name, "type") or "Không rõ"
            )
            output.append(item)
        return output

    ads = []
    for row in reports.get("ads", []):
        item = _metric_row(row)
        ad_group_ad = row.get("adGroupAd") or {}
        ad = ad_group_ad.get("ad") or {}
        responsive = ad.get("responsiveSearchAd") or {}
        item.update(
            {
                "ad_id": str(ad.get("id") or ""),
                "status": ad_group_ad.get("status"),
                "type": ad.get("type"),
                "headlines": [part.get("text") for part in responsive.get("headlines", [])],
                "descriptions": [
                    part.get("text") for part in responsive.get("descriptions", [])
                ],
            }
        )
        ads.append(item)
    return {
        "keywords": keywords,
        "search_terms": search_terms,
        "devices": devices,
        "geography": geography,
        "ages": demographic("ages", "age", "ageRange"),
        "genders": demographic("genders", "gender", "gender"),
        "ads": ads,
        "report_errors": reports.get("_errors", []),
    }


def _flatten_numeric(value: Any, prefix: str = "") -> dict[str, float]:
    output: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            output.update(_flatten_numeric(child, path))
    elif isinstance(value, (int, float, str)):
        parsed = _number(value)
        if parsed is not None:
            if prefix.lower().endswith("micros"):
                parsed /= 1_000_000
            output[prefix] = parsed
    return output


def _change_field(path: str) -> str | None:
    normalized = path.lower()
    if "budget" in normalized:
        return "budget"
    if "bid" in normalized or "cpc" in normalized:
        return "bid"
    if "deposit" in normalized or "payment" in normalized:
        return "deposit"
    return None


def _normalize_change_rows(rows: list[dict], *, campaign_id: int) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        event = row.get("changeEvent") if isinstance(row.get("changeEvent"), dict) else {}
        try:
            changed_at = datetime.fromisoformat(str(event["changeDateTime"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        old_values = _flatten_numeric(event.get("oldResource") or {})
        new_values = _flatten_numeric(event.get("newResource") or {})
        paths = sorted(set(old_values) & set(new_values))
        resource_name = str(event.get("resourceName") or "")
        for path in paths:
            field_name = _change_field(path)
            if field_name is None or old_values[path] == new_values[path]:
                continue
            digest = hashlib.sha256(
                f"{campaign_id}|{resource_name}|{path}|{changed_at.isoformat()}".encode()
            ).hexdigest()
            output.append(
                {
                    "external_id": digest,
                    "field_name": field_name,
                    "old_value": old_values[path],
                    "new_value": new_values[path],
                    "changed_at": _aware(changed_at),
                    "payload_json": {
                        "resource_name": resource_name,
                        "resource_type": event.get("changeResourceType"),
                        "source_path": path,
                        "changed_fields": event.get("changedFields"),
                    },
                }
            )
    return output


def _persist_change_rows(db: Session, campaign_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    existing = set(
        db.scalars(
            select(CampaignChangeEvent.external_id).where(
                CampaignChangeEvent.external_id.in_([item["external_id"] for item in rows])
            )
        ).all()
    )
    for item in rows:
        if item["external_id"] in existing:
            continue
        db.add(CampaignChangeEvent(campaign_id=campaign_id, **item))
    return len(rows) - len(existing)


def _selected_daily_stats(campaign: Campaign) -> list:
    preference = {"GOOGLE_ADS_API": 3, "GOOGLE_ADS_CSV": 2, "GOOGLE_ADS": 1}
    selected = {}
    for item in campaign.daily_stats:
        current = selected.get(item.metric_date)
        score = preference.get(item.source.upper(), 0)
        current_score = preference.get(current.source.upper(), 0) if current else -1
        if current is None or (score, item.updated_at, item.id) > (
            current_score,
            current.updated_at,
            current.id,
        ):
            selected[item.metric_date] = item
    return list(selected.values())


def _selected_spends(campaign: Campaign) -> list:
    preference = {"GOOGLE_ADS_API": 3, "GOOGLE_ADS_CSV": 2, "GOOGLE_ADS": 1}
    selected = {}
    for item in campaign.spends:
        current = selected.get(item.spend_date)
        score = preference.get(item.source.upper(), 0)
        current_score = preference.get(current.source.upper(), 0) if current else -1
        if current is None or (score, item.updated_at, item.id) > (
            current_score,
            current.updated_at,
            current.id,
        ):
            selected[item.spend_date] = item
    return list(selected.values())


def _cost_usd(campaign: Campaign) -> tuple[float | None, str]:
    total = Decimal("0")
    for item in _selected_spends(campaign):
        if item.currency.upper() == "USD":
            total += Decimal(item.amount)
        elif item.normalized_currency == "USD" and item.normalized_amount is not None:
            total += Decimal(item.normalized_amount)
        else:
            return None, "MISSING_USD_FX"
    return float(total), "OBSERVED_USD"


def _commission_feed_for_program(db: Session, program_id: int | None) -> bool:
    if program_id is None:
        return False
    if db.scalar(
        select(func.count(Commission.id))
        .join(Conversion, Commission.conversion_id == Conversion.id)
        .where(Conversion.program_id == program_id)
    ):
        return True
    latest = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == COMMISSION_FOLDER_CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    if latest is None:
        return False
    return any(
        isinstance(item, dict)
        and item.get("program_id") == program_id
        and item.get("status") in SUCCESSFUL_COMMISSION_STATES
        for item in latest.metadata_json.get("file_results", [])
    )


def _direct_refs(db: Session, campaign: Campaign) -> tuple[int | None, str]:
    program_id = campaign.program_link.program_id if campaign.program_link else None
    count = int(
        db.scalar(
            select(func.count(func.distinct(Conversion.id)))
            .join(Click, Conversion.click_id == Click.id)
            .where(Click.campaign_id == campaign.id)
        )
        or 0
    )
    if count:
        return count, "DIRECT_CLICK_ATTRIBUTION"
    if _commission_feed_for_program(db, program_id):
        return 0, "AFFILIATE_FEED_NO_MATCHED_REF"
    return None, "MISSING_AFFILIATE_FEED"


def _campaign_query(campaign_id: int | None = None):
    query = select(Campaign).options(
        joinedload(Campaign.ads_account),
        selectinload(Campaign.daily_stats),
        selectinload(Campaign.spends),
        joinedload(Campaign.program_link).joinedload(CampaignProgramLink.program),
    )
    if campaign_id is not None:
        query = query.where(Campaign.id == campaign_id)
    return query.order_by(Campaign.name, Campaign.id)


def _latest_details(db: Session, campaign_id: int) -> tuple[dict, str | None]:
    item = db.scalar(
        select(CampDiagnosis)
        .where(CampDiagnosis.campaign_id == campaign_id)
        .order_by(CampDiagnosis.run_at.desc(), CampDiagnosis.id.desc())
    )
    if item is None:
        return {}, None
    return dict(item.payload_json.get("details") or {}), item.run_at.isoformat()


def _fetch_details(campaign: Campaign) -> tuple[dict, dict]:
    readiness = google_ads_readiness(Session.object_session(campaign))
    source = {
        "status": readiness["status"],
        "api_version": API_VERSION,
        "write_operations_enabled": False,
    }
    if readiness["status"] != "READY":
        source["message"] = "Chưa đủ credential Google Ads; đang dùng dữ liệu chẩn đoán đã lưu."
        return {}, source
    try:
        access_token = refresh_access_token(
            client_id=read_credential("oauth-client-id"),
            client_secret=read_credential("oauth-client-secret"),
            refresh_token=read_credential("refresh-token"),
        )
        reports = search_campaign_detail_reports(
            customer_id=campaign.ads_account.external_id,
            campaign_external_id=campaign.external_id,
            access_token=access_token,
            developer_token=read_credential("developer-token"),
            login_customer_id=(
                read_credential("login-customer-id")
                if credential_present("login-customer-id")
                else None
            ),
            start_date=date.today() - timedelta(days=DETAIL_LOOKBACK_DAYS - 1),
            end_date=date.today(),
        )
    except (GoogleAdsApiError, RuntimeError) as exc:
        source.update({"status": "ERROR", "message": str(exc)})
        return {}, source
    details = _normalize_details(reports, currency=campaign.currency)
    details["raw_change_events"] = reports.get("change_events", [])
    source.update(
        {
            "status": "LIVE_READ_ONLY",
            "message": "Đã đọc báo cáo chi tiết trực tiếp từ Google Ads.",
            "report_errors": reports.get("_errors", []),
        }
    )
    return details, source


def _diagnosis_payload(
    db: Session,
    campaign: Campaign,
    *,
    details: dict,
    source: dict,
    now: datetime,
) -> dict:
    stats = _selected_daily_stats(campaign)
    impressions = sum(item.impressions for item in stats)
    clicks = sum(item.clicks for item in stats)
    first_date = min((item.metric_date for item in stats), default=None)
    started_at = (
        datetime.combine(first_date, time.min, tzinfo=UTC)
        if first_date
        else _aware(campaign.created_at)
    )
    cost_usd, cost_status = _cost_usd(campaign)
    refs_count, ref_status = _direct_refs(db, campaign)
    diagnosis_refs = refs_count if cost_usd is not None else None

    keyword_states = []
    for item in details.get("keywords", []):
        status = str(item.get("status") or "").upper()
        if status == "ENABLED":
            keyword_states.append(KW_SHOWING)
        elif status in {"PAUSED", "REMOVED"}:
            keyword_states.append(KW_SOMETIMES)
        else:
            keyword_states.append(KW_UNKNOWN)
    impression_shares = [
        item["search_impression_share"]
        for item in details.get("keywords", [])
        if item.get("search_impression_share") is not None
    ]
    competitors = any(value < 0.9 for value in impression_shares)
    average_cpcs = [
        item["average_cpc"]
        for item in details.get("keywords", [])
        if item.get("average_cpc") is not None
    ]
    device_stats = tuple(
        {
            "device": item["device"],
            "clicks": item["clicks"],
            "ctr": (item.get("ctr") or 0) * 100,
            "cost": item.get("cost"),
        }
        for item in details.get("devices", [])
    )
    geo_stats = ()
    if campaign.currency.upper() == "USD":
        geo_stats = tuple(
            {
                "country": item["country"],
                "clicks": item["clicks"],
                "ctr": (item.get("ctr") or 0) * 100,
                "cost": item.get("cost"),
                "refs": None,
            }
            for item in details.get("geography", [])
        )
    change_models = list(
        db.scalars(
            select(CampaignChangeEvent)
            .where(CampaignChangeEvent.campaign_id == campaign.id)
            .order_by(CampaignChangeEvent.changed_at.asc())
        ).all()
    )
    changes = []
    for item in change_models:
        old_value = _number(item.old_value)
        new_value = _number(item.new_value)
        if old_value is not None and new_value is not None:
            changes.append(
                ChangeEvent(item.field_name, old_value, new_value, _aware(item.changed_at))
            )
    snapshot = CampaignSnapshot(
        campaign_id=campaign.id,
        name=campaign.name,
        started_at=started_at,
        impressions=impressions,
        clicks=clicks,
        cost_usd=cost_usd or 0.0,
        refs=diagnosis_refs,
        keyword_states=tuple(keyword_states),
        competitors_on_keyword=competitors,
        avg_cpc_usd=(sum(average_cpcs) / len(average_cpcs) if average_cpcs else None),
        device_stats=device_stats,
        geo_stats=geo_stats,
        # Search-term ref attribution is not available from Google Ads; do not infer zero refs.
        search_terms=(),
    )
    result = diagnose_campaign(snapshot, changes, now).as_dict()
    result.update(
        {
            "campaign_name": campaign.name,
            "campaign_external_id": campaign.external_id,
            "campaign_status": campaign.status,
            "channel_type": campaign.channel_type,
            "account_name": campaign.ads_account.name,
            "currency": campaign.currency,
            "impressions": impressions,
            "clicks": clicks,
            "cost_usd": cost_usd,
            "refs": refs_count,
            "ref_data_status": ref_status,
            "cost_data_status": cost_status,
            "competitors_on_keyword": competitors if impression_shares else None,
            "competitor_inference": (
                "Suy ra từ search impression share <90%; không phải Auction Insights."
                if impression_shares
                else "Chưa có dữ liệu cạnh tranh."
            ),
            "details": {key: value for key, value in details.items() if key != "raw_change_events"},
            "source": source,
            "run_at": now.isoformat(),
            "warning_only": True,
            "project_included": True,
            "google_ads_write_operations_enabled": False,
        }
    )
    return result


def diagnose_one_campaign(
    db: Session,
    campaign_id: int,
    *,
    refresh_api: bool = True,
    persist: bool = True,
    now: datetime | None = None,
) -> dict | None:
    campaign = db.scalar(_campaign_query(campaign_id))
    if campaign is None:
        return None
    now = _aware(now or datetime.now(UTC))
    cached_details, cached_at = _latest_details(db, campaign_id)
    details = cached_details
    source = {
        "status": "CACHE" if cached_details else "LOCAL_ONLY",
        "cached_at": cached_at,
        "write_operations_enabled": False,
    }
    if refresh_api:
        live_details, live_source = _fetch_details(campaign)
        source = live_source
        if live_details:
            details = live_details
            change_rows = _normalize_change_rows(
                live_details.get("raw_change_events", []), campaign_id=campaign.id
            )
            _persist_change_rows(db, campaign.id, change_rows)
            db.flush()
        elif cached_details:
            source["fallback"] = "CACHE"
            source["cached_at"] = cached_at
    payload = _diagnosis_payload(
        db, campaign, details=details, source=source, now=now
    )
    if persist:
        db.add(CampDiagnosis(campaign_id=campaign.id, run_at=now, payload_json=payload))
        db.commit()
    return payload


def diagnose_all_campaigns(db: Session, *, now: datetime | None = None) -> list[dict]:
    now = _aware(now or datetime.now(UTC))
    return [
        _diagnosis_payload(
            db,
            campaign,
            details=_latest_details(db, campaign.id)[0],
            source={
                "status": "CACHE" if _latest_details(db, campaign.id)[0] else "LOCAL_ONLY",
                "cached_at": _latest_details(db, campaign.id)[1],
                "write_operations_enabled": False,
            },
            now=now,
        )
        for campaign in db.scalars(_campaign_query()).unique().all()
    ]
