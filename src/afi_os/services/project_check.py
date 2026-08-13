from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from afi_os.config import PAYBACK_FX_VND_PER_USD
from afi_os.enums import (
    CommissionType,
    DataQuality,
    EvidenceReviewStatus,
)
from afi_os.models import CommercialProposal, CommissionFact, MetricSnapshot, Project
from afi_os.schemas import (
    ProjectCheckCollectionNeed,
    ProjectCheckCommission,
    ProjectCheckCriterion,
    ProjectCheckEvidence,
    ProjectCheckValue,
    ProjectStepOneResponse,
)
from afi_os.services.portfolio import build_portfolio_item
from afi_os.services.programs import (
    commission_resolution_status,
    program_gate_status,
    resolved_permission_for_scope,
)

CLICKS_PER_BUYER = Decimal("150")
PAYBACK_MONTH_DAYS = Decimal("30")
PAYBACK_LIMIT_DAYS = Decimal("120")

FIELD_LABELS = {
    "project_name": "Tên dự án",
    "category": "Ngành dự án",
    "website_url": "Website dự án",
    "affiliate_signup_url": "Link đăng ký affiliate",
    "affiliate_login_url": "Link đăng nhập affiliate",
    "affiliate_ref_url": "Link ref",
    "affiliate_contact_channel": "Kênh liên lạc",
    "affiliate_network": "Affiliate network",
    "website_traffic_monthly": "Traffic website/tháng",
    "google_search_traffic_monthly": "Traffic Google/tháng",
    "primary_keyword": "Từ khóa chính",
    "primary_keyword_search_volume": "Lượt tìm kiếm từ khóa/tháng",
    "primary_keyword_bid_low": "Giá thầu đầu trang thấp",
    "primary_keyword_bid_high": "Giá thầu đầu trang cao",
    "top_traffic_countries": "Quốc gia có traffic cao nhất",
    "financial_license": "Giấy phép ngành tài chính",
    "payout_methods": "Cổng rút hoa hồng",
    "minimum_payout": "Mức rút tối thiểu",
    "payout_timing_days": "Thời gian thanh toán",
    "cookie_days": "Thời hạn cookie",
    "independent_advertisers": "Nhà quảng cáo độc lập",
    "active_advertisers_30d": "Nhà quảng cáo đang chạy 7 ngày",
    "accepted_commission_rate": "Hoa hồng đã xác minh",
    "accepted_commission_flat": "Hoa hồng cố định đã xác minh",
    "accepted_commission_type": "Loại hoa hồng đã xác minh",
    "average_package_price": "Giá gói trung bình",
    "clicks_per_buyer": "Click trung bình cho một người mua",
    "estimated_commission_per_buyer": "Hoa hồng ước tính mỗi người mua",
    "estimated_payback_days_low_bid": "Hoàn vốn ước tính ở bid thấp",
    "estimated_payback_days_high_bid": "Hoàn vốn ước tính ở bid cao",
}

SNAPSHOT_ALIASES = {
    "website_traffic_monthly": (
        "website_traffic_monthly",
        "traffic_monthly",
        "website_monthly_visits",
    ),
    "google_search_traffic_monthly": (
        "google_search_traffic_monthly",
        "google_organic_traffic_monthly",
    ),
    "primary_keyword": ("primary_keyword",),
    "primary_keyword_search_volume": ("primary_keyword_search_volume", "keyword_monthly_searches"),
    "primary_keyword_bid_low": ("primary_keyword_bid_low", "keyword_bid_low"),
    "primary_keyword_bid_high": ("primary_keyword_bid_high", "keyword_bid_high"),
    "top_traffic_countries": ("top_traffic_countries",),
    "affiliate_ref_url": ("affiliate_ref_url",),
    "affiliate_contact_channel": ("affiliate_contact_channel",),
    "affiliate_network": ("affiliate_network",),
    "payout_methods": ("payout_methods",),
    "minimum_payout": ("minimum_payout",),
    "payout_timing_days": ("payout_timing_days",),
    "cookie_days": ("cookie_days",),
    "financial_license": ("financial_license",),
    "average_package_price": ("average_package_price",),
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _missing(key: str, note: str | None = None) -> ProjectCheckValue:
    return ProjectCheckValue(
        key=key,
        label=FIELD_LABELS[key],
        collection_state="NOT_COLLECTED",
        quality=DataQuality.UNKNOWN,
        source_name="Chưa có dữ liệu",
        confidence=0,
        note=note,
    )


def _value(
    key: str,
    value: Any,
    *,
    unit: str | None = None,
    quality: DataQuality = DataQuality.OBSERVED,
    source_name: str,
    source_url: str | None = None,
    observed_at: datetime | None = None,
    confidence: float = 1,
    collection_state: str = "AVAILABLE",
    note: str | None = None,
) -> ProjectCheckValue:
    return ProjectCheckValue(
        key=key,
        label=FIELD_LABELS[key],
        value=value,
        unit=unit,
        quality=quality,
        source_name=source_name,
        source_url=source_url,
        observed_at=observed_at,
        confidence=confidence,
        collection_state=collection_state,
        note=note,
    )


def _latest_snapshots(project: Project) -> dict[str, MetricSnapshot]:
    latest: dict[str, MetricSnapshot] = {}
    for snapshot in project.metric_snapshots:
        current = latest.get(snapshot.metric_key)
        if current is None or (_aware(snapshot.observed_at), snapshot.id) > (
            _aware(current.observed_at),
            current.id,
        ):
            latest[snapshot.metric_key] = snapshot
    return latest


def _snapshot_field(
    key: str, latest: dict[str, MetricSnapshot], *, note: str | None = None
) -> ProjectCheckValue:
    snapshot = next(
        (latest[alias] for alias in SNAPSHOT_ALIASES[key] if alias in latest),
        None,
    )
    if snapshot is None:
        return _missing(key, note)
    value: Any = (
        float(snapshot.numeric_value) if snapshot.numeric_value is not None else snapshot.text_value
    )
    expired = snapshot.valid_until is not None and _aware(snapshot.valid_until) < datetime.now(UTC)
    change_reason = note or (snapshot.payload_json or {}).get("change_reason")
    if expired:
        change_reason = (
            f"Nguồn hết hạn từ {_aware(snapshot.valid_until).date().isoformat()}; "
            "cần kiểm tra lại trước khi quyết định."
        )
    return _value(
        key,
        value,
        unit=snapshot.unit,
        quality=snapshot.quality,
        source_name=snapshot.source_name,
        source_url=snapshot.source_url,
        observed_at=snapshot.observed_at,
        confidence=snapshot.confidence,
        collection_state="STALE" if expired else "AVAILABLE",
        note=change_reason,
    )


def _number(field: ProjectCheckValue) -> Decimal | None:
    if field.value is None:
        return None
    try:
        return Decimal(str(field.value))
    except (ValueError, TypeError):
        return None


def _criterion(
    key: str,
    label: str,
    value: Any,
    threshold: str,
    passed: bool | None,
    explanation: str,
    *,
    warning: bool = False,
) -> ProjectCheckCriterion:
    status = "WARNING" if warning else "UNKNOWN" if passed is None else "PASS" if passed else "FAIL"
    return ProjectCheckCriterion(
        key=key,
        label=label,
        status=status,
        value=value,
        threshold=threshold,
        explanation=explanation,
    )


def _accepted_commission(facts: list[CommissionFact]) -> CommissionFact | None:
    if commission_resolution_status(facts) != "RESOLVED":
        return None
    qualified = [
        fact
        for fact in facts
        if fact.review_status == EvidenceReviewStatus.ACCEPTED
        and fact.confidence >= 0.8
        and (fact.commission_rate is not None or fact.commission_flat is not None)
        and not fact.rate_is_maximum
    ]
    return max(
        qualified,
        key=lambda fact: (_aware(fact.checked_at), fact.id),
        default=None,
    )


def _offer_average(project: Project) -> ProjectCheckValue | None:
    program = project.program
    if program is None:
        return None
    priced = [offer for offer in program.offers if offer.active and offer.price is not None]
    if not priced:
        return None
    currencies = {offer.currency for offer in priced}
    if len(currencies) != 1:
        return None
    average = sum(
        (offer.price for offer in priced if offer.price is not None), Decimal("0")
    ) / Decimal(len(priced))
    sources = {offer.source_url for offer in priced if offer.source_url}
    source_url = next(iter(sources)) if len(sources) == 1 else None
    complete = all(offer.source_url for offer in priced)
    return _value(
        "average_package_price",
        float(average),
        unit=next(iter(currencies)),
        quality=DataQuality.OBSERVED,
        source_name=f"Trung bình {len(priced)} gói giá đã lưu",
        source_url=source_url,
        observed_at=max(offer.updated_at for offer in priced),
        confidence=0.9 if complete else 0.7,
        collection_state="AVAILABLE" if complete else "PARTIAL",
        note=(
            "Công thức lấy giá trung bình tất cả gói giá đã được xác nhận, "
            "không giả định một khách mua ba gói."
        ),
    )


def build_project_step_one(project: Project) -> ProjectStepOneResponse:
    portfolio = build_portfolio_item(project)
    latest = _latest_snapshots(project)
    program = project.program

    fields: dict[str, ProjectCheckValue] = {
        "project_name": _value(
            "project_name",
            project.brand_name,
            source_name="Hồ sơ AFI-OS",
            observed_at=project.updated_at,
        ),
        "category": (
            _value(
                "category",
                project.category,
                source_name="Hồ sơ AFI-OS",
                observed_at=project.updated_at,
            )
            if project.category
            else _missing(
                "category", "Cần nguồn website chính thức hoặc phân loại của người vận hành."
            )
        ),
        "website_url": _value(
            "website_url",
            f"https://{project.domain}",
            source_name="Domain dự án",
            observed_at=project.updated_at,
        ),
        "affiliate_signup_url": (
            _value(
                "affiliate_signup_url",
                program.signup_url,
                source_name="Hồ sơ affiliate program",
                source_url=program.signup_url,
                observed_at=program.updated_at,
            )
            if program and program.signup_url
            else _missing("affiliate_signup_url", "Cần trang đăng ký affiliate chính thức.")
        ),
        "affiliate_login_url": (
            _value(
                "affiliate_login_url",
                program.dashboard_url,
                source_name="Hồ sơ affiliate program",
                source_url=program.dashboard_url,
                observed_at=program.updated_at,
            )
            if program and program.dashboard_url
            else _missing(
                "affiliate_login_url", "Thường chỉ có sau khi đăng ký/đăng nhập partner portal."
            )
        ),
        "affiliate_network": (
            _value(
                "affiliate_network",
                program.network.name,
                source_name="Hồ sơ affiliate program",
                source_url=program.network.base_url,
                observed_at=program.network.updated_at,
            )
            if program and program.network
            else _missing("affiliate_network", "Chưa xác định network hoặc cổng partner.")
        ),
    }

    for key in SNAPSHOT_ALIASES:
        snapshot = _snapshot_field(key, latest)
        if key not in fields or snapshot.value is not None:
            fields[key] = snapshot

    if fields["primary_keyword"].value is None:
        keyword = project.brand_name or project.domain.split(".", 1)[0]
        fields["primary_keyword"] = _value(
            "primary_keyword",
            keyword,
            quality=DataQuality.MODELED,
            source_name="Quy tắc người vận hành",
            confidence=1,
            note=(
                "Từ khóa chính mặc định là tên dự án; volume và bid vẫn phải lấy "
                "từ Keyword Planner."
            ),
        )

    for metric_key in ("independent_advertisers", "active_advertisers_30d"):
        metric = portfolio.metrics[metric_key]
        fields[metric_key] = (
            _value(
                metric_key,
                metric.value,
                unit=metric.unit,
                quality=metric.quality,
                source_name=metric.source_name,
                source_url=metric.source_url,
                observed_at=metric.observed_at,
                confidence=metric.confidence,
                collection_state=metric.collection_state or "NOT_COLLECTED",
                note=metric.change_reason,
            )
            if metric.value is not None
            else _missing(metric_key, metric.change_reason)
        )

    offer_average = _offer_average(project)
    if fields["average_package_price"].value is None and offer_average is not None:
        fields["average_package_price"] = offer_average

    evidence = list(program.terms_evidence) if program else []
    facts = list(program.commission_facts) if program else []
    commercial_proposals: list[CommercialProposal] = (
        list(program.commercial_proposals) if program else []
    )
    permissions = {
        scope: resolved_permission_for_scope(evidence, scope)
        for scope in (
            "PAID_SEARCH",
            "BRAND_KEYWORD",
            "NON_BRAND",
            "DIRECT_LINK",
            "TRADEMARK_AD_COPY",
        )
    }
    gate = program_gate_status(program, evidence) if program else "WARNING_TERMS_UNVERIFIED"
    commission_state = commission_resolution_status(facts)
    accepted = _accepted_commission(facts)
    if accepted is not None:
        fields["accepted_commission_rate"] = (
            _value(
                "accepted_commission_rate",
                float(accepted.commission_rate * 100),
                unit="%",
                source_name="Commission Fact đã chấp nhận",
                source_url=accepted.source_url,
                observed_at=accepted.checked_at,
                confidence=accepted.confidence,
            )
            if accepted.commission_rate is not None
            else _missing("accepted_commission_rate", "Fact đã xác nhận dùng mức cố định.")
        )
        fields["accepted_commission_flat"] = (
            _value(
                "accepted_commission_flat",
                float(accepted.commission_flat),
                unit="USD",
                source_name="Commission Fact đã chấp nhận",
                source_url=accepted.source_url,
                observed_at=accepted.checked_at,
                confidence=accepted.confidence,
            )
            if accepted.commission_flat is not None
            else _missing("accepted_commission_flat", "Fact đã xác nhận dùng tỷ lệ phần trăm.")
        )
        fields["accepted_commission_type"] = _value(
            "accepted_commission_type",
            accepted.commission_type.value,
            source_name="Commission Fact đã chấp nhận",
            source_url=accepted.source_url,
            observed_at=accepted.checked_at,
            confidence=accepted.confidence,
        )
    else:
        fields["accepted_commission_rate"] = _missing(
            "accepted_commission_rate",
            "Chỉ dùng fact ACCEPTED, confidence ≥80%, không phải mức 'up to' và không có conflict.",
        )
        fields["accepted_commission_flat"] = _missing(
            "accepted_commission_flat",
            "Chưa có mức hoa hồng cố định được xác nhận và đủ điều kiện.",
        )
        fields["accepted_commission_type"] = _missing(
            "accepted_commission_type",
            "Commission proposal/conflict không được dùng để tính hoàn vốn.",
        )

    fields["clicks_per_buyer"] = _value(
        "clicks_per_buyer",
        int(CLICKS_PER_BUYER),
        unit="click/người mua",
        quality=DataQuality.MODELED,
        source_name="Công thức người vận hành",
        confidence=1,
        note="Giả định mô hình; sẽ được thay bằng conversion rate thật khi campaign có dữ liệu.",
    )

    avg_price = _number(fields["average_package_price"])
    rate_percent = _number(fields["accepted_commission_rate"])
    commission_flat = _number(fields["accepted_commission_flat"])
    low_bid = _number(fields["primary_keyword_bid_low"])
    high_bid = _number(fields["primary_keyword_bid_high"])
    estimated_commission: Decimal | None = None
    if commission_flat is not None:
        estimated_commission = commission_flat
    elif avg_price is not None and rate_percent is not None:
        estimated_commission = avg_price * rate_percent / Decimal("100")
    if estimated_commission is not None:
        fields["estimated_commission_per_buyer"] = _value(
            "estimated_commission_per_buyer",
            float(estimated_commission),
            unit="USD" if commission_flat is not None else fields["average_package_price"].unit,
            quality=DataQuality.MODELED,
            source_name="Công thức AFI hoàn vốn v1",
            confidence=(
                fields["accepted_commission_flat"].confidence
                if commission_flat is not None
                else min(
                    fields["average_package_price"].confidence,
                    fields["accepted_commission_rate"].confidence,
                )
            ),
            note=(
                "Mức hoa hồng cố định đã xác minh."
                if commission_flat is not None
                else "Giá gói trung bình × % hoa hồng đã xác minh."
            ),
        )
    else:
        fields["estimated_commission_per_buyer"] = _missing(
            "estimated_commission_per_buyer",
            "Thiếu giá gói trung bình hoặc commission đã xác minh.",
        )

    price_currency = (
        "USD"
        if commission_flat is not None
        else (fields["average_package_price"].unit or "").upper()[:3]
    )

    def _scenario_bid(
        bid: Decimal | None,
        factor: str,
        bid_field: ProjectCheckValue,
    ) -> Decimal | None:
        """Apply the operator's sheet scenario and its fixed VND/USD conversion."""
        if bid is None:
            return None
        effective_bid = Decimal(factor) * bid
        bid_currency = (bid_field.unit or "").upper()[:3]
        if not bid_currency or not price_currency:
            return None
        if bid_currency == price_currency:
            return effective_bid
        if bid_currency == "VND" and price_currency == "USD":
            return effective_bid / PAYBACK_FX_VND_PER_USD
        if bid_currency == "USD" and price_currency == "VND":
            return effective_bid * PAYBACK_FX_VND_PER_USD
        return None

    def add_payback(
        key: str,
        bid: Decimal | None,
        factor: str,
        bid_field: ProjectCheckValue,
    ) -> None:
        effective_bid = _scenario_bid(bid, factor, bid_field)
        if effective_bid is None or estimated_commission is None or estimated_commission <= 0:
            fields[key] = _missing(
                key,
                "Thiếu giá thầu hoặc commission đã xác minh để tính hoàn vốn.",
            )
            return
        days = (
            PAYBACK_MONTH_DAYS
            * CLICKS_PER_BUYER
            * effective_bid
            / estimated_commission
        )
        fields[key] = _value(
            key,
            round(float(days), 1),
            unit="ngày",
            quality=DataQuality.MODELED,
            source_name="Công thức AFI hoàn vốn v1",
            confidence=(
                min(fields["accepted_commission_flat"].confidence, bid_field.confidence)
                if commission_flat is not None
                else min(
                    fields["average_package_price"].confidence,
                    fields["accepted_commission_rate"].confidence,
                    bid_field.confidence,
                )
            ),
            note=(
                "30 × 150 × (hệ số×bid ÷ 26.000) ÷ "
                "(giá gói TB × %hoa hồng). Hệ số 3× bid thấp, 0,5× bid cao — "
                "theo sheet gốc. Tỷ giá cố định, sửa tay khi đổi."
            ),
        )

    add_payback(
        "estimated_payback_days_low_bid",
        low_bid,
        "3",
        fields["primary_keyword_bid_low"],
    )
    add_payback(
        "estimated_payback_days_high_bid",
        high_bid,
        "0.5",
        fields["primary_keyword_bid_high"],
    )

    traffic = _number(fields["website_traffic_monthly"])
    volume = _number(fields["primary_keyword_search_volume"])
    payback_high = _number(fields["estimated_payback_days_high_bid"])
    advertiser_count = _number(fields["independent_advertisers"])
    commission_type = fields["accepted_commission_type"].value
    criteria = [
        _criterion(
            "traffic",
            "Traffic website",
            fields["website_traffic_monthly"].value,
            "> 20.000/tháng",
            traffic > 20000 if traffic is not None else None,
            "Nguồn thị trường có ngày quan sát.",
        ),
        _criterion(
            "keyword_volume",
            "Nhu cầu từ khóa chính",
            fields["primary_keyword_search_volume"].value,
            "> 2.000/tháng",
            volume > 2000 if volume is not None else None,
            "Global, English theo Keyword Planner.",
        ),
        _criterion(
            "payback",
            "Hoàn vốn ở bid cao",
            fields["estimated_payback_days_high_bid"].value,
            "≤ 120 ngày",
            payback_high <= PAYBACK_LIMIT_DAYS if payback_high is not None else None,
            "Dùng kịch bản CPC cao để quyết định thận trọng.",
        ),
        _criterion(
            "recurring",
            "Hoa hồng trọn đời",
            commission_type,
            "RECURRING_LIFETIME",
            commission_type == CommissionType.RECURRING_LIFETIME.value if commission_type else None,
            "Điểm cộng; không thay thế bài toán hoàn vốn.",
        ),
        _criterion(
            "advertisers",
            "Nhà quảng cáo độc lập",
            fields["independent_advertisers"].value,
            "> 0 có nguồn",
            advertiser_count > 0 if advertiser_count is not None else None,
            "Số advertiser, không phải số mẫu quảng cáo.",
        ),
        _criterion(
            "ppc_warning",
            "Điều khoản PPC",
            gate,
            "Cảnh báo, không tự loại",
            None,
            "Cấm/mâu thuẫn/chưa rõ vẫn giữ dự án; người vận hành quyết định.",
            warning=gate != "TERMS_OK",
        ),
    ]

    core_fields = [
        "website_traffic_monthly",
        "primary_keyword_search_volume",
        "primary_keyword_bid_low",
        "primary_keyword_bid_high",
        "average_package_price",
        "estimated_payback_days_high_bid",
        "independent_advertisers",
    ]

    def field_is_decision_ready(key: str) -> bool:
        field = fields[key]
        return (
            field.value is not None
            and field.collection_state == "AVAILABLE"
            and field.quality != DataQuality.UNKNOWN
            and field.confidence >= 0.5
        )

    blocking_fields = [FIELD_LABELS[key] for key in core_fields if not field_is_decision_ready(key)]
    commission_ready = field_is_decision_ready(
        "accepted_commission_rate"
    ) or field_is_decision_ready("accepted_commission_flat")
    if not commission_ready:
        blocking_fields.append(FIELD_LABELS["accepted_commission_rate"])
    decision_ready = not blocking_fields

    missing_by_group: dict[str, list[str]] = defaultdict(list)
    for key in (
        "website_traffic_monthly",
        "google_search_traffic_monthly",
        "top_traffic_countries",
    ):
        if fields[key].value is None or fields[key].collection_state != "AVAILABLE":
            missing_by_group["Traffic thị trường"].append(FIELD_LABELS[key])
    for key in (
        "primary_keyword_search_volume",
        "primary_keyword_bid_low",
        "primary_keyword_bid_high",
    ):
        if fields[key].value is None or fields[key].collection_state != "AVAILABLE":
            missing_by_group["Từ khóa & CPC"].append(FIELD_LABELS[key])
    for key in (
        "affiliate_login_url",
        "affiliate_ref_url",
        "affiliate_contact_channel",
        "payout_methods",
        "minimum_payout",
        "payout_timing_days",
    ):
        if fields[key].value is None:
            missing_by_group["Affiliate account"].append(FIELD_LABELS[key])
    if not field_is_decision_ready("average_package_price"):
        missing_by_group["Economics"].append(FIELD_LABELS["average_package_price"])
    if not commission_ready:
        missing_by_group["Economics"].append(FIELD_LABELS["accepted_commission_rate"])
    if not field_is_decision_ready("independent_advertisers"):
        missing_by_group["Quảng cáo thị trường"].append(FIELD_LABELS["independent_advertisers"])
    if fields["category"].value is None or fields["financial_license"].value is None:
        if fields["category"].value is None:
            missing_by_group["Hồ sơ pháp lý"].append(FIELD_LABELS["category"])
        if fields["financial_license"].value is None:
            missing_by_group["Hồ sơ pháp lý"].append(FIELD_LABELS["financial_license"])

    source_requirements = {
        "Traffic thị trường": (
            "Kết nối một lần Apify Similarweb Scraper, Similarweb API hoặc Semrush "
            "Trends API; sau đó AFI-OS "
            "tự lấy theo domain. Cloudflare Radar chỉ bổ sung rank/quốc gia, không thay "
            "được số lượt truy cập tháng."
        ),
        "Từ khóa & CPC": "Google Ads Keyword Planner/API, Customer ID đúng tài khoản",
        "Affiliate account": "Đăng nhập partner portal hoặc API/CSV của affiliate network",
        "Economics": "Trang pricing chính thức + commission fact được người vận hành chấp nhận",
        "Quảng cáo thị trường": (
            "Google Ads Transparency/nguồn spy có URL và snapshot kết quả đầy đủ"
        ),
        "Hồ sơ pháp lý": "Website chính thức và cơ quan cấp phép phù hợp ngành/quốc gia",
    }
    needs = [
        ProjectCheckCollectionNeed(
            group=group,
            fields=missing,
            source_required=source_requirements[group],
            status="NEEDS_CONNECTION"
            if group in {"Traffic thị trường", "Từ khóa & CPC", "Affiliate account"}
            else "NEEDS_SOURCE",
        )
        for group, missing in missing_by_group.items()
    ]

    known = sum(item.status in {"PASS", "FAIL", "WARNING"} for item in criteria)
    passed = sum(item.status == "PASS" for item in criteria)
    readiness = "READY_FOR_STEP_2" if decision_ready else "DATA_INCOMPLETE"
    return ProjectStepOneResponse(
        project_id=project.id,
        program_id=program.id if program else None,
        project_name=project.brand_name,
        domain=project.domain,
        stage=project.stage,
        registration_status=project.registration_status,
        fields=fields,
        permissions=permissions,
        terms_gate_status=gate,
        commission_state=commission_state,
        terms_evidence=[
            ProjectCheckEvidence(
                evidence_id=item.id,
                scope=item.scope,
                decision=item.decision,
                review_status=item.review_status,
                excerpt=item.excerpt,
                summary_vi=item.summary_vi,
                quote_vi=item.quote_vi,
                source_url=item.source_url,
                source_authority=item.source_authority,
                checked_at=item.checked_at,
                confidence=item.confidence,
            )
            for item in sorted(
                evidence, key=lambda entry: (_aware(entry.checked_at), entry.id), reverse=True
            )
        ],
        commission_facts=[
            ProjectCheckCommission(
                commission_fact_id=item.id,
                commission_type=item.commission_type,
                commission_rate=item.commission_rate,
                commission_flat=item.commission_flat,
                recurring_months=item.recurring_months,
                rate_is_maximum=item.rate_is_maximum,
                applies_to=item.applies_to,
                review_status=item.review_status,
                excerpt=item.excerpt,
                summary_vi=item.summary_vi,
                quote_vi=item.quote_vi,
                source_url=item.source_url,
                source_authority=item.source_authority,
                checked_at=item.checked_at,
                confidence=item.confidence,
            )
            for item in sorted(
                facts, key=lambda entry: (_aware(entry.checked_at), entry.id), reverse=True
            )
        ],
        commercial_proposals=sorted(
            commercial_proposals,
            key=lambda entry: (_aware(entry.created_at), entry.id),
            reverse=True,
        ),
        criteria=criteria,
        passed_criteria=passed,
        known_criteria=known,
        total_criteria=len(criteria),
        readiness=readiness,
        decision_ready=decision_ready,
        blocking_fields=blocking_fields,
        collection_needs=needs,
    )
