from __future__ import annotations

import json
from typing import Any

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from afi_os.enums import EvidenceReviewStatus, PermissionStatus
from afi_os.models import AdObservation, Project
from afi_os.schemas import (
    AppraisalAdvertisers,
    AppraisalCommission,
    AppraisalFieldStatus,
    AppraisalFlag,
    AppraisalKeyword,
    AppraisalPayback,
    AppraisalPayment,
    AppraisalResponse,
    AppraisalScore,
    AppraisalTerms,
    AppraisalTraffic,
    ProjectAutoCheckResponse,
    ProjectCheckValue,
)
from afi_os.services.project_check import build_project_step_one


def _value(field: ProjectCheckValue | None) -> Any:
    return field.value if field is not None else None


def _number(field: ProjectCheckValue | None) -> float | None:
    value = _value(field)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(field: ProjectCheckValue | None) -> int | None:
    value = _number(field)
    return int(value) if value is not None else None


def _text(field: ProjectCheckValue | None) -> str | None:
    value = _value(field)
    if value is None or value == "":
        return None
    return str(value)


def _text_list(field: ProjectCheckValue | None) -> list[str] | None:
    value = _value(field)
    if value is None or value == "":
        return None
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
        return result or None
    if isinstance(value, str):
        stripped = value.strip()
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            result = [str(item).strip() for item in parsed if str(item).strip()]
            return result or None
        result = [item.strip() for item in stripped.replace(";", ",").split(",") if item.strip()]
        return result or None
    return [str(value)]


def _countries(field: ProjectCheckValue | None) -> list[tuple[str, float]] | None:
    value = _value(field)
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    items: list[tuple[str, float]] = []
    if isinstance(value, dict):
        value = list(value.items())
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            country = item.get("country") or item.get("code")
            share = item.get("share") or item.get("traffic_share")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            country, share = item[0], item[1]
        else:
            continue
        try:
            normalized_share = float(share)
        except (TypeError, ValueError):
            continue
        if normalized_share > 1:
            normalized_share /= 100
        items.append((str(country).upper(), normalized_share))
    return items or None


def _also_running(db: Session, project: Project) -> list[str] | None:
    advertiser_ids = list(
        db.scalars(
            select(distinct(AdObservation.advertiser_id)).where(
                AdObservation.project_id == project.id
            )
        ).all()
    )
    if not advertiser_ids:
        return None
    domains = list(
        db.scalars(
            select(distinct(Project.domain))
            .join(AdObservation, AdObservation.project_id == Project.id)
            .where(
                AdObservation.advertiser_id.in_(advertiser_ids),
                Project.id != project.id,
            )
            .order_by(Project.domain.asc())
        ).all()
    )
    return domains or []


def _offer_packages(project: Project) -> list[tuple[str, float]] | None:
    if project.program is None:
        return None
    result = []
    for offer in project.program.offers:
        if not offer.active or offer.price is None:
            continue
        result.append((offer.name, float(offer.price)))
    return result or None


def _commission_type(value: str | None) -> str | None:
    return {
        "ONE_TIME": "one_time",
        "RECURRING_LIFETIME": "recurring",
        "RECURRING_FIXED_TERM": "recurring_fixed_term",
        "FLAT": "flat",
    }.get(value or "", value.lower() if value else None)


def _commission_display(
    project: Project,
    commission_type: str | None,
    commission_percent: float | None,
) -> tuple[str | None, float | None, bool]:
    """Return an operator-accepted commission for display, not for payback.

    Step 1 deliberately excludes an accepted `up to` rate from economics. The
    appraisal contract must still show that accepted commercial fact, with a
    warning, so a known 50% recurring maximum is not rendered as missing.
    """

    if commission_type is not None and commission_percent is not None:
        return _commission_type(commission_type), commission_percent, False
    if project.program is None:
        return None, None, False
    accepted = [
        fact
        for fact in project.program.commission_facts
        if fact.review_status == EvidenceReviewStatus.ACCEPTED
        and fact.confidence >= 0.8
        and fact.commission_rate is not None
    ]
    fact = max(accepted, key=lambda item: (item.checked_at, item.id), default=None)
    if fact is None:
        return None, None, False
    return (
        _commission_type(fact.commission_type.value),
        float(fact.commission_rate * 100),
        fact.rate_is_maximum,
    )


def _cookie_days(project: Project, fields: dict) -> int | None:  # type: ignore[type-arg]
    extracted = _integer(fields.get("cookie_days"))
    if extracted is not None:
        return extracted
    if project.program is None:
        return None
    values = [
        offer.cookie_days
        for offer in project.program.offers
        if offer.active and offer.cookie_days
    ]
    return max(values) if values else None


def _payment_net(project: Project) -> str | None:
    if project.program is None or project.program.network is None:
        return None
    return project.program.network.name


def _permission_boolean(value: PermissionStatus) -> bool | None:
    if value in {PermissionStatus.BRAND_ALLOWED, PermissionStatus.NON_BRAND_ONLY}:
        return True
    if value == PermissionStatus.PROHIBITED:
        return False
    return None


def score_appraisal(
    resp_traffic: AppraisalTraffic,
    resp_keyword: AppraisalKeyword,
    resp_payback: AppraisalPayback,
    resp_commission: AppraisalCommission,
    resp_terms: AppraisalTerms,
    base_flags: list[AppraisalFlag],
) -> AppraisalScore:
    """Score source-backed appraisal facts without turning warnings into exclusions."""
    traffic_min, search_min, payback_max = 20_000, 2_000, 120
    flags = list(base_flags)

    traffic = resp_traffic.monthly
    search_volume = resp_keyword.search_volume
    paybacks = [
        days
        for days in (resp_payback.days_low, resp_payback.days_high)
        if days is not None
    ]
    commission_type = resp_commission.type or ""

    traffic_ok = traffic is not None and traffic > traffic_min
    search_ok = search_volume is not None and search_volume > search_min
    payback_known = bool(paybacks)
    payback_ok = payback_known and min(paybacks) <= payback_max
    recurring = commission_type.startswith("recurring")

    total = (
        (25 if traffic_ok else 0)
        + (35 if search_ok else 0)
        + (30 if payback_ok else 0)
        + (10 if recurring else 0)
    )

    if traffic is None:
        flags.append(
            AppraisalFlag(level="pending", msg="Traffic đang chờ nguồn (Apify/Similarweb).")
        )
    elif not traffic_ok:
        flags.append(
            AppraisalFlag(level="warning", msg=f"Traffic {int(traffic):,} < 20.000.")
        )
    if search_volume is None:
        flags.append(
            AppraisalFlag(level="pending", msg="Chưa có lượt tìm kiếm từ khoá chính.")
        )
    elif not search_ok:
        flags.append(
            AppraisalFlag(level="warning", msg=f"Search {int(search_volume):,} < 2.000.")
        )
    if not payback_known:
        flags.append(AppraisalFlag(level="pending", msg="Chưa tính được hoàn vốn."))
    elif not payback_ok:
        flags.append(AppraisalFlag(level="warning", msg="Hoàn vốn > 120 ngày."))
    if resp_terms.ads_allowed is False:
        flags.append(
            AppraisalFlag(
                level="warning",
                msg="Điều khoản CẤM chạy Google Ads — rủi ro quỵt tiền (chỉ cảnh báo).",
            )
        )
    if resp_terms.brand_bid_restricted:
        flags.append(AppraisalFlag(level="warning", msg="Cấm bid từ khoá thương hiệu."))
    if commission_type == "one_time":
        flags.append(
            AppraisalFlag(
                level="warning",
                msg="Hoa hồng one-time — hoàn vốn kém tin cậy, tính NET/chu kỳ.",
            )
        )

    core: list[bool | None] = [
        traffic_ok if traffic is not None else None,
        search_ok if search_volume is not None else None,
        payback_ok if payback_known else None,
    ]
    if any(item is False for item in core):
        passed = False
    elif any(item is None for item in core):
        passed = None
    else:
        passed = True

    return AppraisalScore(total=int(total), pass_=passed, flags=flags)


def build_appraisal_contract(
    db: Session,
    project: Project,
    auto_check: ProjectAutoCheckResponse | None = None,
    *,
    job_id: int | None = None,
    job_status: str | None = None,
    field_statuses: dict[str, AppraisalFieldStatus | dict] | None = None,
) -> AppraisalResponse:
    """Map collected facts into the stable Dot1.1 contract.

    Missing providers remain explicit nulls; the score reflects only available facts.
    """

    step = auto_check.step_one if auto_check is not None else build_project_step_one(project)
    fields = step.fields
    traffic_field = fields.get("website_traffic_monthly")
    countries_field = fields.get("top_traffic_countries")
    traffic_monthly = _number(traffic_field)
    countries = _countries(countries_field)
    traffic_state = "ready" if traffic_monthly is not None and countries is not None else (
        "partial" if traffic_monthly is not None or countries is not None else "pending"
    )
    traffic_source = next(
        (
            item.source
            for item in (auto_check.sources if auto_check is not None else [])
            if item.source.lower().startswith("traffic website")
        ),
        traffic_field.source_name if traffic_field and traffic_monthly is not None else None,
    )

    paid_search = step.permissions.get("PAID_SEARCH", PermissionStatus.NOT_CHECKED)
    non_brand = step.permissions.get("NON_BRAND", PermissionStatus.NOT_CHECKED)
    brand = step.permissions.get("BRAND_KEYWORD", PermissionStatus.NOT_CHECKED)
    ads_allowed = _permission_boolean(paid_search)
    if ads_allowed is None:
        ads_allowed = _permission_boolean(non_brand)
    brand_restricted = (
        True
        if brand == PermissionStatus.PROHIBITED
        else False
        if brand == PermissionStatus.BRAND_ALLOWED
        else None
    )
    evidence = step.terms_evidence
    terms_summary = (
        "; ".join(item.excerpt.strip() for item in evidence[:3] if item.excerpt.strip())[:1000]
        or f"{step.terms_gate_status}; PPC chưa đủ bằng chứng vẫn là cảnh báo."
    )
    terms_source = evidence[0].source_url if evidence else None

    score_flags: list[AppraisalFlag] = []
    if step.terms_gate_status != "TERMS_OK":
        score_flags.append(
            AppraisalFlag(
                level="warning",
                msg="Điều khoản PPC chưa đủ bằng chứng; chỉ cảnh báo, không loại dự án.",
            )
        )

    commission_type = _text(fields.get("accepted_commission_type"))
    commission_percent = _number(fields.get("accepted_commission_rate"))
    commission_type, commission_percent, commission_is_maximum = _commission_display(
        project,
        commission_type,
        commission_percent,
    )
    if commission_is_maximum:
        score_flags.append(
            AppraisalFlag(
                level="warning",
                msg=(
                    "Hoa hồng đã xác nhận là mức tối đa; hiển thị fact nhưng chưa dùng "
                    "để tính hoàn vốn."
                ),
            )
        )
    payout_days = _integer(fields.get("payout_timing_days"))
    traffic = AppraisalTraffic(
        monthly=traffic_monthly,
        top_countries=countries,
        source=traffic_source,
        source_status=traffic_state,
    )
    keyword = AppraisalKeyword(
        term=_text(fields.get("primary_keyword")),
        search_volume=_number(fields.get("primary_keyword_search_volume")),
        bid_low_vnd=_number(fields.get("primary_keyword_bid_low")),
        bid_high_vnd=_number(fields.get("primary_keyword_bid_high")),
        source=(
            fields["primary_keyword_search_volume"].source_name
            if _value(fields.get("primary_keyword_search_volume")) is not None
            else None
        ),
    )
    commission = AppraisalCommission(
        type=commission_type,
        percent=commission_percent,
        packages=_offer_packages(project),
        avg_package=_number(fields.get("average_package_price")),
    )
    terms = AppraisalTerms(
        ads_allowed=ads_allowed,
        brand_bid_restricted=brand_restricted,
        summary=terms_summary,
        source=terms_source,
    )
    payback = AppraisalPayback(
        days_low=_number(fields.get("estimated_payback_days_low_bid")),
        days_high=_number(fields.get("estimated_payback_days_high_bid")),
        mode=("AFI v1 · 150 clicks/buyer" if step.decision_ready else None),
    )
    return AppraisalResponse(
        domain=project.domain,
        niche=project.category,
        affiliate_link=(project.program.signup_url if project.program else None),
        traffic=traffic,
        keyword=keyword,
        advertisers=AppraisalAdvertisers(
            count=_integer(fields.get("active_advertisers_30d")),
            active_count=_integer(fields.get("active_advertisers_30d")),
            total_ever=_integer(fields.get("independent_advertisers")),
            also_running=_also_running(db, project),
            source=(
                fields["independent_advertisers"].source_name
                if _value(fields.get("independent_advertisers")) is not None
                else None
            ),
        ),
        commission=commission,
        payment=AppraisalPayment(
            gateways=_text_list(fields.get("payout_methods")),
            min_payment=_number(fields.get("minimum_payout")),
            clear_days=payout_days,
            cookie_days=_cookie_days(project, fields),
            net=_text(fields.get("affiliate_network")) or _payment_net(project),
        ),
        terms=terms,
        payback=payback,
        score=score_appraisal(
            traffic,
            keyword,
            payback,
            commission,
            terms,
            score_flags,
        ),
        job_id=job_id,
        job_status=job_status,
        field_statuses=field_statuses or {},
    )
