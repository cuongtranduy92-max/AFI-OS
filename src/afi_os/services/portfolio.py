from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from afi_os.enums import DataQuality, EvidenceReviewStatus
from afi_os.models import Campaign, MetricSnapshot, Program, Project
from afi_os.schemas import MetricEnvelope, ProjectPortfolioItem
from afi_os.services.programs import (
    commission_resolution_status,
    latest_research_run,
    program_gate_status,
)

METRIC_LABELS = {
    "independent_advertisers": "Nhà quảng cáo độc lập",
    "active_advertisers_30d": "Nhà quảng cáo hoạt động 30 ngày",
    "campaigns": "Campaign đã liên kết",
    "impressions": "Lượt hiển thị",
    "clicks": "Lượt nhấp",
    "conversions": "Lượt chuyển đổi",
    "ctr": "CTR",
    "cost": "Chi phí quảng cáo",
    "commission": "Commission đã xác nhận",
    "terms_status": "Trạng thái điều khoản PPC",
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _latest_datetime(values: list[datetime | None]) -> datetime | None:
    aware_values = [_aware(value) for value in values if value is not None]
    return max(aware_values) if aware_values else None


def _decimal_to_number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _metric(
    key: str,
    value: int | float | str | None,
    *,
    unit: str | None = None,
    quality: DataQuality = DataQuality.UNKNOWN,
    source_name: str = "Chưa có dữ liệu",
    source_url: str | None = None,
    observed_at: datetime | None = None,
    confidence: float = 0.0,
    date_from: date | None = None,
    date_to: date | None = None,
    method_version: str = "portfolio-derived-v1",
    collection_state: str | None = None,
    previous_value: int | float | str | None = None,
    change_reason: str | None = None,
    lineage: list[dict[str, Any]] | None = None,
    valid_until: datetime | None = None,
    geography: str | None = None,
    language: str | None = None,
) -> MetricEnvelope:
    return MetricEnvelope(
        key=key,
        label=METRIC_LABELS.get(key, key.replace("_", " ").title()),
        value=value,
        unit=unit,
        quality=quality,
        source_name=source_name,
        source_url=source_url,
        observed_at=observed_at,
        valid_until=valid_until,
        confidence=confidence,
        geography=geography,
        language=language,
        date_from=date_from,
        date_to=date_to,
        method_version=method_version,
        collection_state=(
            collection_state
            if collection_state is not None
            else "AVAILABLE"
            if value is not None
            else "NOT_COLLECTED"
        ),
        previous_value=previous_value,
        change_reason=change_reason,
        lineage=lineage or [],
    )


def portfolio_query():  # type: ignore[no-untyped-def]
    """Return the canonical eager-load query used by list and detail endpoints."""

    return select(Project).options(
        selectinload(Project.program).selectinload(Program.merchant),
        selectinload(Project.program).selectinload(Program.terms_evidence),
        selectinload(Project.program).selectinload(Program.commission_facts),
        selectinload(Project.program).selectinload(Program.terms_research_runs),
        selectinload(Project.program).selectinload(Program.offers),
        selectinload(Project.program).selectinload(Program.network),
        selectinload(Project.observations),
        selectinload(Project.campaigns).selectinload(Campaign.ads_account),
        selectinload(Project.campaigns).selectinload(Campaign.daily_stats),
        selectinload(Project.campaigns).selectinload(Campaign.spends),
        selectinload(Project.metric_snapshots),
        selectinload(Project.camp_plan),
    )


def load_portfolio_projects(db: Session) -> list[Project]:
    return list(
        db.scalars(portfolio_query().order_by(Project.updated_at.desc(), Project.id.desc())).all()
    )


def load_portfolio_project(db: Session, project_id: int) -> Project | None:
    return db.scalar(portfolio_query().where(Project.id == project_id))


def _observation_metrics(project: Project) -> dict[str, MetricEnvelope]:
    observations = list(project.observations)
    if not observations:
        return {
            "independent_advertisers": _metric(
                "independent_advertisers",
                None,
                collection_state="NOT_COLLECTED",
                change_reason=("Chưa thu thập advertiser cho dự án này; đây không phải là 0."),
            ),
            "active_advertisers_30d": _metric(
                "active_advertisers_30d",
                None,
                collection_state="NOT_COLLECTED",
                change_reason="Chưa có snapshot quảng cáo để tính cửa sổ 30 ngày.",
            ),
        }

    advertiser_ids = {item.advertiser_id for item in observations}
    cutoff = datetime.now(UTC).date() - timedelta(days=30)
    observations_by_advertiser: dict[int, list[Any]] = defaultdict(list)
    for observation in observations:
        observations_by_advertiser[observation.advertiser_id].append(observation)
    activity_complete = all(
        any(item.last_seen_at is not None for item in advertiser_observations)
        for advertiser_observations in observations_by_advertiser.values()
    )
    active_ids = {
        item.advertiser_id
        for item in observations
        if item.last_seen_at is not None and _aware(item.last_seen_at).date() >= cutoff
    }
    observed_at = _latest_datetime([item.last_seen_at or item.created_at for item in observations])
    date_from = min(item.snapshot_date for item in observations)
    date_to = max(item.snapshot_date for item in observations)
    source_urls = Counter(item.source_url for item in observations if item.source_url)
    source_details: dict[str, dict[str, Any]] = {}
    result_set_complete = False
    imported_result_set = False
    confidences: list[float] = []
    for item in observations:
        metadata = item.metadata_json or {}
        url = item.source_url
        detail = source_details.setdefault(
            url,
            {
                "source_url": url,
                "source_name": metadata.get("source_name"),
                "source_authority": metadata.get("source_authority"),
                "observation_count": 0,
                "reported_ad_count": 0,
                "result_set_complete": False,
                "checked_at": metadata.get("checked_at"),
            },
        )
        detail["observation_count"] += 1
        detail["reported_ad_count"] += int(metadata.get("reported_ad_count") or 0)
        detail["result_set_complete"] = bool(
            detail["result_set_complete"] or metadata.get("result_set_complete")
        )
        result_set_complete = result_set_complete or bool(metadata.get("result_set_complete"))
        imported_result_set = imported_result_set or (
            metadata.get("evidence_type") == "ADVERTISER_RESULT_SET"
        )
        try:
            confidences.append(float(metadata.get("confidence")))
        except (TypeError, ValueError):
            pass
    lineage = list(source_details.values())[:20]
    source_names = {str(item.get("source_name")) for item in lineage if item.get("source_name")}
    source_name = (
        next(iter(source_names))
        if len(source_names) == 1
        else "Ad observations có nguồn trong AFI-OS"
    )
    source_url = next(iter(source_urls)) if len(source_urls) == 1 else None
    count_collection_state = "AVAILABLE" if result_set_complete else "PARTIAL"
    count_confidence = min(confidences) if confidences else 0.6
    common: dict[str, Any] = {
        "quality": DataQuality.IMPORTED if imported_result_set else DataQuality.OBSERVED,
        "source_name": source_name,
        "source_url": source_url,
        "observed_at": observed_at,
        "confidence": count_confidence,
        "date_from": date_from,
        "date_to": date_to,
        "lineage": lineage,
    }
    return {
        "independent_advertisers": _metric(
            "independent_advertisers",
            len(advertiser_ids),
            collection_state=count_collection_state,
            change_reason=(
                None
                if result_set_complete
                else (
                    "Số đang thấy là mức tối thiểu từ các snapshot đã nhập, "
                    "chưa phải toàn thị trường."
                )
            ),
            **common,
        ),
        "active_advertisers_30d": _metric(
            "active_advertisers_30d",
            len(active_ids) if activity_complete else None,
            collection_state="AVAILABLE" if activity_complete else "PARTIAL",
            change_reason=(
                None
                if activity_complete
                else (
                    "Nguồn chưa cung cấp last_seen cho đủ advertiser; "
                    "không được suy diễn thành 0 hoạt động."
                )
            ),
            **common,
        ),
    }


def _campaign_metrics(project: Project) -> dict[str, MetricEnvelope]:
    campaigns = list(project.campaigns)
    missing = {
        "campaigns": _metric(
            "campaigns",
            None,
            change_reason="Chưa có campaign nào được liên kết với dự án.",
        ),
        "impressions": _metric("impressions", None),
        "clicks": _metric("clicks", None),
        "conversions": _metric("conversions", None),
        "ctr": _metric(
            "ctr",
            None,
            unit="%",
            change_reason="Cần dữ liệu impression và click theo ngày.",
        ),
        "cost": _metric("cost", None),
    }
    if not campaigns:
        return missing

    campaign_lineage = [
        {
            "campaign_id": item.id,
            "google_ads_campaign_id": item.external_id,
            "campaign": item.name,
            "status": item.status,
            "customer_id": item.ads_account.external_id if item.ads_account else None,
        }
        for item in campaigns
    ]
    latest_campaign_at = _latest_datetime([item.updated_at for item in campaigns])
    metrics = dict(missing)
    metrics["campaigns"] = _metric(
        "campaigns",
        len(campaigns),
        quality=DataQuality.MATCHED,
        source_name="Liên kết campaign nội bộ AFI-OS",
        observed_at=latest_campaign_at,
        confidence=1.0,
        lineage=campaign_lineage,
    )

    daily_stats = [stat for campaign in campaigns for stat in campaign.daily_stats]
    if daily_stats:
        impressions = sum(item.impressions for item in daily_stats)
        clicks = sum(item.clicks for item in daily_stats)
        conversions = sum((item.conversions for item in daily_stats), Decimal("0"))
        metric_dates = [item.metric_date for item in daily_stats]
        observed_at = _latest_datetime([item.updated_at for item in daily_stats])
        source_counts = Counter(item.source for item in daily_stats)
        lineage = campaign_lineage + [
            {"source": source, "daily_row_count": count}
            for source, count in source_counts.most_common()
        ]
        common = {
            "quality": DataQuality.OBSERVED,
            "source_name": "Google Ads daily stats",
            "observed_at": observed_at,
            "confidence": 1.0,
            "date_from": min(metric_dates),
            "date_to": max(metric_dates),
            "lineage": lineage,
        }
        metrics["impressions"] = _metric("impressions", impressions, **common)
        metrics["clicks"] = _metric("clicks", clicks, **common)
        metrics["conversions"] = _metric("conversions", _decimal_to_number(conversions), **common)
        ctr = (clicks / impressions * 100) if impressions else 0.0
        metrics["ctr"] = _metric("ctr", round(ctr, 4), unit="%", **common)

    spends = [spend for campaign in campaigns for spend in campaign.spends]
    if spends:
        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for spend in spends:
            totals[spend.currency] += spend.amount
        spend_dates = [item.spend_date for item in spends]
        observed_at = _latest_datetime([item.updated_at for item in spends])
        if len(totals) == 1:
            currency, total = next(iter(totals.items()))
            value: float | str = float(total)
            unit = currency
        else:
            value = " + ".join(
                f"{float(amount):,.2f} {currency}" for currency, amount in sorted(totals.items())
            )
            unit = None
        metrics["cost"] = _metric(
            "cost",
            value,
            unit=unit,
            quality=DataQuality.IMPORTED,
            source_name="Google Ads cost import",
            observed_at=observed_at,
            confidence=1.0,
            date_from=min(spend_dates),
            date_to=max(spend_dates),
            lineage=campaign_lineage,
        )
    return metrics


def _terms_and_commission_metrics(
    project: Project,
) -> tuple[dict[str, MetricEnvelope], str, str]:
    program = project.program
    if program is None:
        return (
            {
                "terms_status": _metric(
                    "terms_status",
                    "NOT_CHECKED",
                    change_reason="Dự án chưa liên kết affiliate program.",
                ),
                "commission": _metric(
                    "commission",
                    None,
                    change_reason="Chưa có affiliate program để đọc commission.",
                ),
            },
            "WARNING_TERMS_UNVERIFIED",
            "NOT_CHECKED",
        )

    evidence = list(program.terms_evidence)
    facts = list(program.commission_facts)
    gate = program_gate_status(program, evidence)
    commission_state = commission_resolution_status(facts)
    accepted_evidence = [
        item for item in evidence if item.review_status == EvidenceReviewStatus.ACCEPTED
    ]
    latest_evidence_at = _latest_datetime([item.checked_at for item in evidence])
    terms_lineage = [
        {
            "evidence_id": item.id,
            "scope": item.scope,
            "decision": item.decision.value,
            "review_status": item.review_status.value,
            "source_authority": item.source_authority.value,
            "source_url": item.source_url,
            "checked_at": item.checked_at.isoformat(),
            "confidence": item.confidence,
        }
        for item in sorted(evidence, key=lambda entry: entry.checked_at, reverse=True)
    ]
    latest_evidence = max(evidence, key=lambda item: item.checked_at, default=None)
    terms_metric = _metric(
        "terms_status",
        gate,
        quality=(DataQuality.OBSERVED if accepted_evidence else DataQuality.UNKNOWN),
        source_name=("Terms Evidence" if evidence else "Chưa có bằng chứng PPC đủ điều kiện"),
        source_url=(latest_evidence.source_url if latest_evidence else None),
        observed_at=latest_evidence_at,
        confidence=(max(item.confidence for item in accepted_evidence) if accepted_evidence else 0),
        method_version="terms-gate-v1",
        lineage=terms_lineage,
    )

    qualified_accepted = [
        fact
        for fact in facts
        if fact.review_status == EvidenceReviewStatus.ACCEPTED and fact.confidence >= 0.8
    ]
    latest_fact = max(
        qualified_accepted,
        key=lambda fact: (_aware(fact.checked_at), fact.id),
        default=None,
    )
    fact_lineage = [
        {
            "commission_fact_id": fact.id,
            "commission_type": fact.commission_type.value,
            "commission_rate": (
                str(fact.commission_rate) if fact.commission_rate is not None else None
            ),
            "rate_is_maximum": fact.rate_is_maximum,
            "applies_to": fact.applies_to,
            "review_status": fact.review_status.value,
            "source_authority": fact.source_authority.value,
            "source_url": fact.source_url,
            "checked_at": fact.checked_at.isoformat(),
            "confidence": fact.confidence,
        }
        for fact in sorted(facts, key=lambda entry: entry.checked_at, reverse=True)
    ]
    if commission_state == "RESOLVED" and latest_fact is not None:
        rate = (
            float(latest_fact.commission_rate) * 100
            if latest_fact.commission_rate is not None
            else None
        )
        commission_metric = _metric(
            "commission",
            rate,
            unit="%" if rate is not None else None,
            quality=DataQuality.OBSERVED,
            source_name="Commission Fact đã chấp nhận",
            source_url=latest_fact.source_url,
            observed_at=latest_fact.checked_at,
            confidence=latest_fact.confidence,
            method_version="commission-resolution-v1",
            change_reason=(f"{latest_fact.commission_type.value} · {latest_fact.applies_to}"),
            lineage=fact_lineage,
        )
    else:
        commission_metric = _metric(
            "commission",
            commission_state if commission_state == "CONFLICT" else None,
            quality=DataQuality.UNKNOWN,
            source_name="Commission Facts chưa được giải quyết",
            observed_at=_latest_datetime([fact.checked_at for fact in facts]),
            method_version="commission-resolution-v1",
            change_reason=(
                "Nguồn commission đang mâu thuẫn."
                if commission_state == "CONFLICT"
                else "Cần người vận hành chấp nhận một fact có nguồn."
            ),
            lineage=fact_lineage,
        )
    return {"terms_status": terms_metric, "commission": commission_metric}, gate, commission_state


def _snapshot_metric(snapshot: MetricSnapshot, previous: MetricSnapshot | None) -> MetricEnvelope:
    value: int | float | str | None
    if snapshot.numeric_value is not None:
        value = float(snapshot.numeric_value)
    else:
        value = snapshot.text_value
    previous_value: int | float | str | None = None
    if previous is not None:
        previous_value = (
            float(previous.numeric_value)
            if previous.numeric_value is not None
            else previous.text_value
        )
    lineage = [
        {
            "metric_snapshot_id": snapshot.id,
            "source_hash": snapshot.source_hash,
            "payload": snapshot.payload_json,
        }
    ]
    return _metric(
        snapshot.metric_key,
        value,
        unit=snapshot.unit,
        quality=snapshot.quality,
        source_name=snapshot.source_name,
        source_url=snapshot.source_url,
        observed_at=snapshot.observed_at,
        valid_until=snapshot.valid_until,
        confidence=snapshot.confidence,
        geography=snapshot.geography,
        language=snapshot.language,
        date_from=snapshot.date_from,
        date_to=snapshot.date_to,
        method_version=snapshot.method_version,
        previous_value=previous_value,
        change_reason=(snapshot.payload_json or {}).get("change_reason"),
        lineage=lineage,
    )


def _apply_snapshots(metrics: dict[str, MetricEnvelope], snapshots: list[MetricSnapshot]) -> None:
    grouped: dict[str, list[MetricSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.metric_key].append(snapshot)
    for key, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (_aware(item.observed_at), item.id),
            reverse=True,
        )
        metrics[key] = _snapshot_metric(ordered[0], ordered[1] if len(ordered) > 1 else None)


def _risk_badges(
    project: Project,
    metrics: dict[str, MetricEnvelope],
    gate: str,
    commission_state: str,
) -> list[str]:
    badges: list[str] = []
    if project.registration_status.value == "BLOCKED_REGISTRATION":
        badges.append("REGISTRATION_BLOCKED")
    if gate == "WARNING_TERMS_CONFLICT":
        badges.append("PPC_CONFLICT")
    elif gate == "WARNING_TERMS_PROHIBITED":
        badges.append("PPC_PROHIBITED")
    elif gate != "TERMS_OK":
        badges.append("PPC_NOT_CHECKED")
    if commission_state == "CONFLICT":
        badges.append("COMMISSION_CONFLICT")
    elif commission_state != "RESOLVED":
        badges.append("COMMISSION_REVIEW_REQUIRED")
    if metrics["independent_advertisers"].value is None:
        badges.append("ADVERTISER_DATA_MISSING")
    if metrics["campaigns"].value is None:
        badges.append("CAMPAIGN_DATA_MISSING")
    ctr = metrics["ctr"].value
    if isinstance(ctr, (int, float)) and ctr < 40:
        badges.append("CTR_BELOW_40")
    return badges


def build_portfolio_item(project: Project) -> ProjectPortfolioItem:
    metrics = _observation_metrics(project)
    metrics.update(_campaign_metrics(project))
    terms_metrics, gate, commission_state = _terms_and_commission_metrics(project)
    metrics.update(terms_metrics)
    _apply_snapshots(metrics, list(project.metric_snapshots))

    program = project.program
    latest_run = latest_research_run(program.terms_research_runs) if program else None
    components = {
        "identity": 20 if project.domain and project.brand_name else 0,
        "affiliate_program": 20 if program is not None else 0,
        "terms_research": (
            20 if latest_run is not None or (program and program.terms_evidence) else 0
        ),
        "commission": 20 if commission_state == "RESOLVED" else 0,
        "market_or_campaign_data": (
            20
            if metrics["independent_advertisers"].value is not None
            or metrics["campaigns"].value is not None
            else 0
        ),
    }
    return ProjectPortfolioItem(
        id=project.id,
        domain=project.domain,
        brand_name=project.brand_name,
        category=project.category,
        watch_status=project.watch_status,
        stage=project.stage,
        registration_status=project.registration_status,
        owner=project.owner,
        next_action=project.next_action,
        next_action_due_at=project.next_action_due_at,
        program_id=program.id if program else None,
        program_name=program.name if program else None,
        program_status=program.status if program else None,
        signup_url=program.signup_url if program else None,
        terms_gate_status=gate,
        commission_state=commission_state,
        opportunity_potential=None,
        opportunity_state="DATA_INCOMPLETE",
        evidence_confidence=sum(components.values()),
        confidence_components=components,
        risk_badges=_risk_badges(project, metrics, gate, commission_state),
        project_included=True,
        metrics=metrics,
        updated_at=project.updated_at,
    )
