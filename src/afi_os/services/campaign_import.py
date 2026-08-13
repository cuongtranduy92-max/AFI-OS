from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, DataQuality, SyncStatus
from afi_os.models import (
    AdsAccount,
    AuditLog,
    Campaign,
    CampaignDailyStat,
    CampaignProgramLink,
    Merchant,
    Program,
    Spend,
    SyncRun,
)
from afi_os.schemas import normalize_domain
from afi_os.services.commission_import import decode_csv, detect_delimiter, normalize_key
from afi_os.services.currency import apply_currency_normalization


@dataclass(frozen=True)
class ParsedCampaignMetric:
    account_external_id: str
    account_id_explicit: bool
    account_name: str
    campaign_external_id: str
    campaign_name: str
    campaign_status: str
    channel_type: str
    daily_budget: Decimal | None
    currency: str
    metric_date: date
    cost: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    source: str
    program_domain: str | None
    provided_fields: frozenset[str]
    source_row_number: int


ALIASES: dict[str, tuple[str, ...]] = {
    "account_external_id": (
        "customer_id",
        "account_id",
        "google_ads_account_id",
        "id_khach_hang",
    ),
    "account_name": ("account_name", "customer_name", "account", "ten_tai_khoan"),
    "campaign_external_id": ("campaign_id", "campaign_external_id", "id_chien_dich"),
    "campaign_name": ("campaign", "campaign_name", "chien_dich"),
    "campaign_status": (
        "campaign_state",
        "campaign_status",
        "trang_thai_chien_dich",
        "status",
    ),
    "channel_type": (
        "campaign_type",
        "channel_type",
        "advertising_channel_type",
        "type",
        "loai_chien_dich",
    ),
    "daily_budget": ("daily_budget", "budget", "campaign_budget", "ngan_sach"),
    "currency": ("currency", "currency_code", "ma_don_vi_tien_te"),
    "metric_date": ("date", "day", "metric_date", "ngay"),
    "cost": ("cost", "spend", "amount", "cost_micros", "chi_phi"),
    "impressions": ("impressions", "impr", "so_luot_hien_thi"),
    "clicks": ("clicks", "luot_nhap"),
    "conversions": ("conversions", "conv", "all_conversions", "luot_chuyen_doi"),
    "program_domain": ("program_domain", "merchant_domain", "affiliate_domain"),
}

GOOGLE_ADS_SOURCE = "GOOGLE_ADS_CSV"
PLACEHOLDERS = {"", "--", "—"}
CAMPAIGN_REPORT_REQUIRED_FIELDS = (
    "campaign_external_id",
    "campaign_name",
    "metric_date",
    "cost",
)
CAMPAIGN_REPORT_TRAFFIC_FIELDS = ("impressions", "clicks", "conversions")
CAMPAIGN_REPORT_CONTEXT_FIELDS = ("campaign_status", "channel_type", "currency")
CAMPAIGN_REPORT_FIELD_LABELS = {
    "campaign_external_id": "Campaign ID",
    "campaign_name": "Campaign",
    "metric_date": "Date / Ngày",
    "cost": "Cost / Chi phí",
}
COMMISSION_HEADER_MARKERS = {
    "affiliate_subid",
    "commission",
    "commission_amount",
    "commission_id",
    "commission_state",
    "earnings",
    "gclid",
    "google_click_id",
    "hoa_hong",
    "order_amount",
    "order_id",
    "order_value",
    "payout",
    "sale_amount",
    "sub_id",
    "subid",
    "subid1",
    "transaction_id",
}
CAMPAIGN_STATUS_MAP = {
    "active": "ENABLED",
    "dang_bat": "ENABLED",
    "enabled": "ENABLED",
    "paused": "PAUSED",
    "tam_dung": "PAUSED",
    "removed": "REMOVED",
    "da_xoa": "REMOVED",
}
CHANNEL_TYPE_MAP = {
    "display": "DISPLAY",
    "hien_thi": "DISPLAY",
    "performance_max": "PERFORMANCE_MAX",
    "search": "SEARCH",
    "shopping": "SHOPPING",
    "tim_kiem": "SEARCH",
    "video": "VIDEO",
}


def _parse_decimal(value: str, field: str, *, default: Decimal | None = None) -> Decimal:
    raw = (value or "").strip().replace("\u00a0", "").replace(" ", "")
    if not raw:
        if default is not None:
            return default
        raise ValueError(f"{field} bị trống")
    raw = raw.replace("%", "")
    if "," in raw and "." in raw:
        raw = (
            raw.replace(",", "")
            if raw.rfind(".") > raw.rfind(",")
            else raw.replace(".", "").replace(",", ".")
        )
    elif "," in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", ".") if len(tail) <= 2 else raw.replace(",", "")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{field} không phải số hợp lệ: {value}") from exc
    if result < 0:
        raise ValueError(f"{field} không được âm")
    return result


def _parse_int(value: str, field: str) -> int:
    number = _parse_decimal(value, field, default=Decimal("0"))
    if number != number.to_integral_value():
        raise ValueError(f"{field} phải là số nguyên")
    return int(number)


def _parse_date(value: str) -> date:
    raw = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Ngày không hợp lệ: {value}")


def _normalized_google_ads_customer_id(value: str) -> str:
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return raw


def _header_map(fieldnames: list[str]) -> dict[str, str | None]:
    normalized = {normalize_key(name): name for name in fieldnames if name}
    return {
        target: next((normalized[alias] for alias in aliases if alias in normalized), None)
        for target, aliases in ALIASES.items()
    }


def _cell(row: dict[str, str], mapping: dict[str, str | None], key: str) -> str:
    source = mapping.get(key)
    return (row.get(source, "") if source else "").strip()


def _provided_fields(
    row: dict[str, str], mapping: dict[str, str | None]
) -> frozenset[str]:
    return frozenset(
        key
        for key in ALIASES
        if mapping.get(key) is not None and _cell(row, mapping, key) not in PLACEHOLDERS
    )


def _row_provides(row: ParsedCampaignMetric, field: str) -> bool:
    return field in row.provided_fields


def _effective_currency(
    row: ParsedCampaignMetric,
    account: AdsAccount | None,
    campaign: Campaign | None,
) -> str:
    if _row_provides(row, "currency"):
        return row.currency
    if campaign is not None and campaign.currency:
        return campaign.currency
    if account is not None and account.currency:
        return account.currency
    return row.currency


def _canonical_source(source: str) -> str:
    normalized = normalize_key(source).upper()
    if normalized.startswith("GOOGLE_ADS"):
        return GOOGLE_ADS_SOURCE
    return normalized or GOOGLE_ADS_SOURCE


def _source_matches(model: type[Spend] | type[CampaignDailyStat], source: str):
    if source == GOOGLE_ADS_SOURCE:
        return func.upper(model.source).like("GOOGLE_ADS%")
    return model.source == source


def _locate_header(text: str) -> tuple[list[str], list[list[str]], int]:
    rows = list(csv.reader(io.StringIO(text), delimiter=detect_delimiter(text)))
    if not rows:
        raise ValueError("CSV không có hàng tiêu đề")

    required = CAMPAIGN_REPORT_REQUIRED_FIELDS
    best_index = 0
    best_score = -1
    for index, candidate in enumerate(rows[:50]):
        mapping = _header_map(candidate)
        score = sum(mapping[field] is not None for field in required)
        if score > best_score:
            best_index = index
            best_score = score
        if score == len(required):
            break
    return rows[best_index], rows[best_index + 1 :], best_index + 2


def inspect_campaign_report_signature(data: bytes) -> dict[str, Any]:
    """Classify a bounded CSV prefix without trusting its filename."""
    try:
        fieldnames, _rows, _first_data_line = _locate_header(decode_csv(data))
    except (csv.Error, ValueError):
        return {
            "is_report": False,
            "is_near_match": False,
            "is_campaign_id_recoverable": False,
            "has_customer_id_column": False,
            "missing_fields": list(CAMPAIGN_REPORT_REQUIRED_FIELDS),
            "missing_columns": [
                CAMPAIGN_REPORT_FIELD_LABELS[field]
                for field in CAMPAIGN_REPORT_REQUIRED_FIELDS
            ],
        }
    mapping = _header_map(fieldnames)
    missing_fields = [
        field
        for field in CAMPAIGN_REPORT_REQUIRED_FIELDS
        if mapping[field] is None
    ]
    traffic_count = sum(
        mapping[field] is not None for field in CAMPAIGN_REPORT_TRAFFIC_FIELDS
    )
    context_count = sum(
        mapping[field] is not None for field in CAMPAIGN_REPORT_CONTEXT_FIELDS
    )
    normalized_headers = {normalize_key(field) for field in fieldnames if field}
    has_commission_marker = bool(normalized_headers & COMMISSION_HEADER_MARKERS)
    is_report = not missing_fields and traffic_count >= 2
    has_customer_id_column = mapping["account_external_id"] is not None
    is_campaign_id_recoverable = bool(
        missing_fields == ["campaign_external_id"]
        and has_customer_id_column
        and traffic_count >= 2
        and not has_commission_marker
    )
    is_near_match = bool(
        not is_report
        and not is_campaign_id_recoverable
        and mapping["campaign_name"] is not None
        and mapping["cost"] is not None
        and traffic_count >= 2
        and context_count >= 2
        and not has_commission_marker
    )
    return {
        "is_report": is_report,
        "is_near_match": is_near_match,
        "is_campaign_id_recoverable": is_campaign_id_recoverable,
        "has_customer_id_column": has_customer_id_column,
        "missing_fields": missing_fields,
        "missing_columns": [
            CAMPAIGN_REPORT_FIELD_LABELS[field] for field in missing_fields
        ],
        "traffic_column_count": traffic_count,
        "context_column_count": context_count,
        "has_commission_marker": has_commission_marker,
    }


def looks_like_campaign_report(data: bytes) -> bool:
    """Recognize a complete campaign metrics export without trusting its filename."""
    return bool(inspect_campaign_report_signature(data)["is_report"])


def _row_dict(fieldnames: list[str], values: list[str]) -> dict[str, str]:
    return {
        field: values[index] if index < len(values) else ""
        for index, field in enumerate(fieldnames)
        if field
    }


def _is_ignored_google_ads_row(
    row: dict[str, str], mapping: dict[str, str | None]
) -> bool:
    values = [str(value).strip() for value in row.values() if value is not None]
    if not any(values):
        return True
    campaign_id = _cell(row, mapping, "campaign_external_id")
    has_total_marker = any(
        normalize_key(value).startswith("tong_so") for value in values
    )
    return campaign_id in PLACEHOLDERS and has_total_marker


def _normalized_campaign_status(value: str) -> str:
    raw = (value or "UNKNOWN").strip()
    return CAMPAIGN_STATUS_MAP.get(normalize_key(raw), raw.upper())


def _normalized_channel_type(value: str) -> str:
    raw = (value or "SEARCH").strip()
    return CHANNEL_TYPE_MAP.get(normalize_key(raw), raw.upper())


def parse_campaign_rows(
    data: bytes,
    source: str,
    account_external_id: str,
    account_name: str,
    *,
    allow_missing_campaign_id: bool = False,
) -> tuple[list[ParsedCampaignMetric], list[dict[str, Any]], int]:
    text = decode_csv(data)
    fieldnames, raw_rows, first_data_line = _locate_header(text)
    mapping = _header_map(fieldnames)
    required = CAMPAIGN_REPORT_REQUIRED_FIELDS
    missing = [
        field
        for field in required
        if mapping[field] is None
        and not (allow_missing_campaign_id and field == "campaign_external_id")
    ]
    if missing:
        raise ValueError("Thiếu cột bắt buộc: " + ", ".join(missing))

    normalized_source = _canonical_source(source)
    fallback_account_id = account_external_id.strip()
    fallback_account_name = account_name.strip() or "Google Ads CSV"
    parsed: list[ParsedCampaignMetric] = []
    errors: list[dict[str, Any]] = []
    rows_read = 0
    cost_header = normalize_key(mapping["cost"] or "")
    for row_number, values in enumerate(raw_rows, start=first_data_line):
        row = _row_dict(fieldnames, values)
        if _is_ignored_google_ads_row(row, mapping):
            continue
        rows_read += 1
        try:
            provided_fields = _provided_fields(row, mapping)
            explicit_account_id = _cell(row, mapping, "account_external_id")
            row_account_id = _normalized_google_ads_customer_id(
                explicit_account_id or fallback_account_id
            )
            if not row_account_id:
                raise ValueError("Thiếu Customer ID; nhập ở form hoặc thêm cột customer_id")
            campaign_id = _cell(row, mapping, "campaign_external_id")
            campaign_name = _cell(row, mapping, "campaign_name")
            if not campaign_name:
                raise ValueError("Tên campaign bị trống")
            if not campaign_id and not allow_missing_campaign_id:
                raise ValueError("Campaign ID bị trống")
            cost = _parse_decimal(_cell(row, mapping, "cost"), "cost")
            if cost_header == "cost_micros":
                cost /= Decimal("1000000")
            domain_raw = _cell(row, mapping, "program_domain")
            parsed.append(
                ParsedCampaignMetric(
                    account_external_id=row_account_id,
                    account_id_explicit=bool(explicit_account_id),
                    account_name=_cell(row, mapping, "account_name") or fallback_account_name,
                    campaign_external_id=campaign_id,
                    campaign_name=campaign_name,
                    campaign_status=_normalized_campaign_status(
                        _cell(row, mapping, "campaign_status")
                    ),
                    channel_type=_normalized_channel_type(
                        _cell(row, mapping, "channel_type")
                    ),
                    daily_budget=(
                        _parse_decimal(_cell(row, mapping, "daily_budget"), "daily_budget")
                        if "daily_budget" in provided_fields
                        else None
                    ),
                    currency=(_cell(row, mapping, "currency") or "USD").upper()[:3],
                    metric_date=_parse_date(_cell(row, mapping, "metric_date")),
                    cost=cost,
                    impressions=_parse_int(_cell(row, mapping, "impressions"), "impressions"),
                    clicks=_parse_int(_cell(row, mapping, "clicks"), "clicks"),
                    conversions=_parse_decimal(
                        _cell(row, mapping, "conversions"),
                        "conversions",
                        default=Decimal("0"),
                    ),
                    source=normalized_source,
                    program_domain=normalize_domain(domain_raw) if domain_raw else None,
                    provided_fields=provided_fields,
                    source_row_number=row_number,
                )
            )
        except ValueError as exc:
            errors.append({"row": row_number, "message": str(exc)})
    return parsed, errors, rows_read


def _program_maps(db: Session) -> tuple[dict[int, Program], dict[str, Program]]:
    programs = list(db.scalars(select(Program)).all())
    by_id = {item.id: item for item in programs}
    merchant_by_id = {item.id: item for item in db.scalars(select(Merchant)).all()}
    candidates: defaultdict[str, list[Program]] = defaultdict(list)
    for item in programs:
        merchant = merchant_by_id.get(item.merchant_id)
        if merchant is not None:
            candidates[merchant.website_domain.lower()].append(item)
    by_domain = {
        domain: items[0] for domain, items in candidates.items() if len(items) == 1
    }
    return by_id, by_domain


def _domain_in_campaign_name(domain: str, campaign_name: str) -> bool:
    return bool(
        re.search(
            rf"(?<![a-z0-9-]){re.escape(domain.lower())}(?![a-z0-9-])",
            campaign_name.lower(),
        )
    )


def _resolved_program_for_row(
    row: ParsedCampaignMetric,
    *,
    programs_by_id: dict[int, Program],
    programs_by_domain: dict[str, Program],
    default_program_id: int | None,
) -> tuple[Program | None, str | None]:
    if row.program_domain:
        explicit = programs_by_domain.get(row.program_domain.lower())
        return (explicit, "PROGRAM_DOMAIN") if explicit else (None, None)
    if default_program_id is not None:
        default = programs_by_id.get(default_program_id)
        return (default, "DEFAULT_PROGRAM") if default else (None, None)
    matches = [
        program
        for domain, program in programs_by_domain.items()
        if _domain_in_campaign_name(domain, row.campaign_name)
    ]
    if len(matches) == 1:
        return matches[0], "CAMPAIGN_NAME_DOMAIN"
    return None, None


def _campaign_metric_key(row: ParsedCampaignMetric) -> tuple[str, str, date, str]:
    return (
        row.account_external_id,
        row.campaign_external_id,
        row.metric_date,
        row.source,
    )


def _normalized_campaign_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def analyze_campaign_import(
    db: Session,
    data: bytes,
    source: str,
    account_external_id: str,
    account_name: str,
    default_program_id: int | None,
) -> dict[str, Any]:
    identity_rows, errors, rows_read = parse_campaign_rows(
        data,
        source,
        account_external_id,
        account_name,
        allow_missing_campaign_id=True,
    )
    programs_by_id, programs_by_domain = _program_maps(db)
    if default_program_id is not None and default_program_id not in programs_by_id:
        raise ValueError("Chương trình mặc định không tồn tại")

    accounts = {
        item.external_id: item
        for item in db.scalars(
            select(AdsAccount).where(
                AdsAccount.external_id.in_(
                    {row.account_external_id for row in identity_rows}
                )
            )
        ).all()
    } if identity_rows else {}
    account_ids = [item.id for item in accounts.values()]
    campaign_items = (
        list(
            db.scalars(
                select(Campaign).where(Campaign.ads_account_id.in_(account_ids))
            ).all()
        )
        if account_ids
        else []
    )
    campaigns = {
        (item.ads_account_id, item.external_id): item
        for item in campaign_items
    }
    campaigns_by_account_name: defaultdict[tuple[int, str], list[Campaign]] = (
        defaultdict(list)
    )
    for campaign in campaign_items:
        campaigns_by_account_name[
            (campaign.ads_account_id, _normalized_campaign_name(campaign.name))
        ].append(campaign)

    resolution_attempted = 0
    resolution_resolved = 0
    resolution_unresolved = 0
    parsed: list[ParsedCampaignMetric] = []
    for row in identity_rows:
        if row.campaign_external_id:
            parsed.append(row)
            continue
        resolution_attempted += 1
        if not row.account_id_explicit:
            resolution_unresolved += 1
            errors.append(
                {
                    "row": row.source_row_number,
                    "message": (
                        "Thiếu Campaign ID; chỉ được tự khôi phục khi dòng có "
                        "Customer ID trực tiếp"
                    ),
                }
            )
            continue
        account = accounts.get(row.account_external_id)
        if account is None:
            resolution_unresolved += 1
            errors.append(
                {
                    "row": row.source_row_number,
                    "message": (
                        "Thiếu Campaign ID và Customer ID không thuộc tài khoản "
                        "AFI-OS đã cấu hình"
                    ),
                }
            )
            continue
        matches = campaigns_by_account_name.get(
            (account.id, _normalized_campaign_name(row.campaign_name)),
            [],
        )
        if len(matches) != 1:
            resolution_unresolved += 1
            detail = "không khớp campaign đã lưu" if not matches else "khớp nhiều campaign"
            errors.append(
                {
                    "row": row.source_row_number,
                    "message": (
                        f"Thiếu Campaign ID; tên campaign {detail} trong Customer ID "
                        f"{row.account_external_id}"
                    ),
                }
            )
            continue
        parsed.append(
            replace(row, campaign_external_id=matches[0].external_id)
        )
        resolution_resolved += 1

    seen: set[tuple[str, str, date, str]] = set()
    rows: list[ParsedCampaignMetric] = []
    duplicates_in_file = 0
    for item in parsed:
        key = (
            item.account_external_id,
            item.campaign_external_id,
            item.metric_date,
            item.source,
        )
        if key in seen:
            duplicates_in_file += 1
            continue
        seen.add(key)
        rows.append(item)

    new_rows = 0
    update_rows = 0
    duplicates_existing = 0
    mapped_rows = 0
    auto_mapped_rows = 0
    resolved_programs: dict[
        tuple[str, str, date, str], tuple[Program, str]
    ] = {}
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        resolved_program, resolution_source = _resolved_program_for_row(
            row,
            programs_by_id=programs_by_id,
            programs_by_domain=programs_by_domain,
            default_program_id=default_program_id,
        )
        account = accounts.get(row.account_external_id)
        campaign = campaigns.get((account.id, row.campaign_external_id)) if account else None
        effective_currency = _effective_currency(row, account, campaign)
        totals[effective_currency] += row.cost
        link = (
            db.scalar(
                select(CampaignProgramLink).where(
                    CampaignProgramLink.campaign_id == campaign.id
                )
            )
            if campaign
            else None
        )
        if resolved_program is not None and resolution_source is not None:
            resolved_programs[_campaign_metric_key(row)] = (
                resolved_program,
                resolution_source,
            )
            if (
                resolution_source == "CAMPAIGN_NAME_DOMAIN"
                and (link is None or link.program_id is None)
            ):
                auto_mapped_rows += 1
        if resolved_program is not None or link is not None and link.program_id is not None:
            mapped_rows += 1
        if campaign is None:
            new_rows += 1
            continue
        spend = db.scalar(
            select(Spend).where(
                Spend.campaign_id == campaign.id,
                Spend.spend_date == row.metric_date,
                _source_matches(Spend, row.source),
            )
        )
        stats = db.scalar(
            select(CampaignDailyStat).where(
                CampaignDailyStat.campaign_id == campaign.id,
                CampaignDailyStat.metric_date == row.metric_date,
                _source_matches(CampaignDailyStat, row.source),
            )
        )
        unchanged = (
            campaign.name == row.campaign_name
            and (
                not _row_provides(row, "account_name")
                or account is not None and account.name == row.account_name
            )
            and (
                not _row_provides(row, "campaign_status")
                or campaign.status == row.campaign_status
            )
            and (
                not _row_provides(row, "channel_type")
                or campaign.channel_type == row.channel_type
            )
            and (
                not _row_provides(row, "currency")
                or campaign.currency == row.currency
            )
            and (
                not _row_provides(row, "daily_budget")
                or Decimal(campaign.daily_budget or 0) == Decimal(row.daily_budget or 0)
            )
            and spend is not None
            and Decimal(spend.amount) == row.cost
            and spend.currency == effective_currency
            and stats is not None
            and stats.impressions == row.impressions
            and stats.clicks == row.clicks
            and Decimal(stats.conversions) == row.conversions
            and (
                resolved_program is None
                or link is not None and link.program_id == resolved_program.id
                or (
                    resolution_source == "CAMPAIGN_NAME_DOMAIN"
                    and link is not None
                    and link.program_id is not None
                )
                or (
                    link is not None
                    and link.program_id is not None
                    and link.link_source == "MANUAL"
                )
            )
        )
        if unchanged:
            duplicates_existing += 1
        else:
            update_rows += 1

    return {
        "source": _canonical_source(source),
        "rows_read": rows_read,
        "valid_rows": len(rows),
        "new_rows": new_rows,
        "update_rows": update_rows,
        "duplicates_existing": duplicates_existing,
        "duplicates_in_file": duplicates_in_file,
        "error_count": len(errors),
        "errors": errors[:20],
        "mapped_rows": mapped_rows,
        "unmapped_rows": len(rows) - mapped_rows,
        "auto_mapped_rows": auto_mapped_rows,
        "campaign_id_resolution": {
            "method": "EXACT_CUSTOMER_AND_CAMPAIGN_NAME",
            "attempted_rows": resolution_attempted,
            "resolved_rows": resolution_resolved,
            "unresolved_rows": resolution_unresolved,
        },
        "totals_by_currency": {key: str(value) for key, value in sorted(totals.items())},
        "total_impressions": sum(row.impressions for row in rows),
        "total_clicks": sum(row.clicks for row in rows),
        "total_conversions": str(sum((row.conversions for row in rows), Decimal("0"))),
        "metric_date_from": min((row.metric_date for row in rows), default=None),
        "metric_date_to": max((row.metric_date for row in rows), default=None),
        "_identity_rows": identity_rows,
        "_rows": rows,
        "_programs_by_id": programs_by_id,
        "_programs_by_domain": programs_by_domain,
        "_default_program_id": default_program_id,
        "_resolved_programs": resolved_programs,
    }


def _set_if_changed(item: Any, field: str, value: Any) -> bool:
    if getattr(item, field) == value:
        return False
    setattr(item, field, value)
    return True


def backfill_campaign_domain_mappings(
    db: Session,
    *,
    actor: str = "auto-maintenance",
) -> dict[str, int]:
    """Map only unlinked campaigns whose names identify one unique merchant domain."""
    _, programs_by_domain = _program_maps(db)
    campaigns = list(db.scalars(select(Campaign).order_by(Campaign.id.asc())).all())
    mapped = 0
    unresolved = 0
    preserved_existing = 0

    for campaign in campaigns:
        link = db.scalar(
            select(CampaignProgramLink).where(
                CampaignProgramLink.campaign_id == campaign.id
            )
        )
        if link is not None and link.program_id is not None:
            preserved_existing += 1
            continue
        matches = [
            program
            for domain, program in programs_by_domain.items()
            if _domain_in_campaign_name(domain, campaign.name)
        ]
        if len(matches) != 1:
            unresolved += 1
            continue
        program = matches[0]
        if link is None:
            audit_action = AuditAction.CREATE
            db.add(
                CampaignProgramLink(
                    campaign_id=campaign.id,
                    program_id=program.id,
                    link_source="CAMPAIGN_NAME_DOMAIN",
                )
            )
        else:
            audit_action = AuditAction.UPDATE
            link.program_id = program.id
            link.link_source = "CAMPAIGN_NAME_DOMAIN"
        db.add(
            AuditLog(
                entity_type="campaign_program_link",
                entity_id=str(campaign.id),
                action=audit_action,
                actor=actor,
                payload_json={
                    "program_id": program.id,
                    "link_source": "CAMPAIGN_NAME_DOMAIN",
                    "permissions_changed": False,
                    "campaign_state_changed": False,
                },
            )
        )
        mapped += 1

    db.commit()
    return {
        "campaigns_total": len(campaigns),
        "unlinked_scanned": len(campaigns) - preserved_existing,
        "mapped": mapped,
        "unresolved": unresolved,
        "preserved_existing": preserved_existing,
    }


def commit_campaign_import(
    db: Session,
    analysis: dict[str, Any],
    *,
    actor: str = "operator",
    connector: str = "GOOGLE_ADS_CSV",
    link_source: str = "CSV",
    sync_metadata: dict[str, Any] | None = None,
) -> int:
    rows: list[ParsedCampaignMetric] = analysis["_rows"]
    programs_by_id: dict[int, Program] = analysis["_programs_by_id"]
    programs_by_domain: dict[str, Program] = analysis["_programs_by_domain"]
    default_program_id: int | None = analysis["_default_program_id"]
    resolved_programs: dict[
        tuple[str, str, date, str], tuple[Program, str]
    ] = analysis.get("_resolved_programs", {})
    accounts: dict[str, AdsAccount] = {}
    campaigns: dict[tuple[int, str], Campaign] = {}
    links: dict[int, CampaignProgramLink] = {}
    written = 0
    now = datetime.now(UTC)

    for row in rows:
        account = accounts.get(row.account_external_id) or db.scalar(
            select(AdsAccount).where(AdsAccount.external_id == row.account_external_id)
        )
        row_changed = False
        if account is None:
            account = AdsAccount(
                external_id=row.account_external_id,
                name=row.account_name,
                currency=row.currency,
                status="ACTIVE",
            )
            db.add(account)
            db.flush()
            row_changed = True
        else:
            if _row_provides(row, "account_name"):
                row_changed |= _set_if_changed(account, "name", row.account_name)
            if _row_provides(row, "currency"):
                row_changed |= _set_if_changed(account, "currency", row.currency)
        account.last_synced_at = now
        accounts[row.account_external_id] = account

        campaign_key = (account.id, row.campaign_external_id)
        campaign = campaigns.get(campaign_key) or db.scalar(
            select(Campaign).where(
                Campaign.ads_account_id == account.id,
                Campaign.external_id == row.campaign_external_id,
            )
        )
        if campaign is None:
            campaign_currency = _effective_currency(row, account, None)
            campaign = Campaign(
                ads_account_id=account.id,
                external_id=row.campaign_external_id,
                name=row.campaign_name,
                status=row.campaign_status,
                channel_type=row.channel_type,
                daily_budget=row.daily_budget,
                currency=campaign_currency,
                launch_gate_status="WARNING_ONLY",
            )
            db.add(campaign)
            db.flush()
            row_changed = True
        else:
            row_changed |= _set_if_changed(campaign, "name", row.campaign_name)
            if _row_provides(row, "campaign_status"):
                row_changed |= _set_if_changed(campaign, "status", row.campaign_status)
            if _row_provides(row, "channel_type"):
                row_changed |= _set_if_changed(campaign, "channel_type", row.channel_type)
            if _row_provides(row, "daily_budget"):
                row_changed |= _set_if_changed(campaign, "daily_budget", row.daily_budget)
            if _row_provides(row, "currency"):
                row_changed |= _set_if_changed(campaign, "currency", row.currency)
            row_changed |= _set_if_changed(campaign, "launch_gate_status", "WARNING_ONLY")
        campaigns[campaign_key] = campaign

        resolved = resolved_programs.get(_campaign_metric_key(row))
        if resolved is None:
            resolved_program, resolution_source = _resolved_program_for_row(
                row,
                programs_by_id=programs_by_id,
                programs_by_domain=programs_by_domain,
                default_program_id=default_program_id,
            )
        else:
            resolved_program, resolution_source = resolved
        if resolved_program is not None:
            link = links.get(campaign.id)
            if link is None:
                link = db.scalar(
                    select(CampaignProgramLink).where(
                        CampaignProgramLink.campaign_id == campaign.id
                    )
                )
            if link is None:
                link = CampaignProgramLink(
                    campaign_id=campaign.id,
                    program_id=resolved_program.id,
                    link_source=(
                        "CAMPAIGN_NAME_DOMAIN"
                        if resolution_source == "CAMPAIGN_NAME_DOMAIN"
                        else link_source
                    ),
                )
                db.add(link)
                row_changed = True
            elif link.program_id is None:
                row_changed |= _set_if_changed(link, "program_id", resolved_program.id)
                row_changed |= _set_if_changed(
                    link,
                    "link_source",
                    (
                        "CAMPAIGN_NAME_DOMAIN"
                        if resolution_source == "CAMPAIGN_NAME_DOMAIN"
                        else link_source
                    ),
                )
            elif (
                link.program_id != resolved_program.id
                and link.link_source != "MANUAL"
                and resolution_source != "CAMPAIGN_NAME_DOMAIN"
            ):
                row_changed |= _set_if_changed(link, "program_id", resolved_program.id)
                row_changed |= _set_if_changed(link, "link_source", link_source)
            links[campaign.id] = link

        spend = db.scalar(
            select(Spend).where(
                Spend.campaign_id == campaign.id,
                Spend.spend_date == row.metric_date,
                _source_matches(Spend, row.source),
            )
        )
        if spend is None:
            db.add(
                Spend(
                    campaign_id=campaign.id,
                    spend_date=row.metric_date,
                    amount=row.cost,
                    currency=campaign.currency,
                    source=row.source,
                    quality=DataQuality.OBSERVED,
                )
            )
            row_changed = True
        else:
            row_changed |= _set_if_changed(spend, "amount", row.cost)
            row_changed |= _set_if_changed(spend, "currency", campaign.currency)
            row_changed |= _set_if_changed(spend, "quality", DataQuality.OBSERVED)

        stats = db.scalar(
            select(CampaignDailyStat).where(
                CampaignDailyStat.campaign_id == campaign.id,
                CampaignDailyStat.metric_date == row.metric_date,
                _source_matches(CampaignDailyStat, row.source),
            )
        )
        if stats is None:
            db.add(
                CampaignDailyStat(
                    campaign_id=campaign.id,
                    metric_date=row.metric_date,
                    impressions=row.impressions,
                    clicks=row.clicks,
                    conversions=row.conversions,
                    source=row.source,
                    quality=DataQuality.OBSERVED,
                )
            )
            row_changed = True
        else:
            row_changed |= _set_if_changed(stats, "impressions", row.impressions)
            row_changed |= _set_if_changed(stats, "clicks", row.clicks)
            row_changed |= _set_if_changed(stats, "conversions", row.conversions)
            row_changed |= _set_if_changed(stats, "quality", DataQuality.OBSERVED)
        if row_changed:
            written += 1

    db.flush()
    normalization = apply_currency_normalization(db)
    db.add(
        SyncRun(
            connector=connector,
            started_at=now,
            ended_at=datetime.now(UTC),
            status=SyncStatus.SUCCESS,
            rows_read=analysis["rows_read"],
            rows_written=written,
            metadata_json={
                "mapped_rows": analysis["mapped_rows"],
                "unmapped_rows": analysis["unmapped_rows"],
                "auto_mapped_rows": analysis.get("auto_mapped_rows", 0),
                "source": analysis["source"],
                "normalized_rows": normalization["normalized_rows"],
                "missing_fx_rows": normalization["missing_rows"],
                **(sync_metadata or {}),
            },
        )
    )
    db.add(
        AuditLog(
            entity_type="campaign_import",
            entity_id=now.isoformat(),
            action=AuditAction.IMPORT,
            actor=actor,
            payload_json={"rows_read": analysis["rows_read"], "rows_written": written},
        )
    )
    db.commit()
    return written
