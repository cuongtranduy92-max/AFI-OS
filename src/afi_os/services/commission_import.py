from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from afi_os.enums import CommissionState, DataQuality
from afi_os.models import Click, Commission, Conversion
from afi_os.services.currency import apply_currency_normalization
from afi_os.services.reconciliation import (
    record_conflict,
    record_duplicate,
    record_import_conflict,
    sync_commission_reconciliation,
)


@dataclass(frozen=True)
class ParsedCommission:
    raw_external_id: str
    external_id: str
    amount: Decimal
    currency: str
    state: CommissionState
    occurred_at: datetime
    source: str
    click_ref: str | None
    click_ref_type: str | None
    order_value: Decimal | None
    raw_hash: str


ALIASES: dict[str, tuple[str, ...]] = {
    "external_id": ("external_id", "transaction_id", "transaction", "id", "commission_id", "order_id"),
    "amount": ("amount", "commission", "commission_amount", "payout", "earnings", "hoa_hong"),
    "currency": ("currency", "currency_code", "tien_te"),
    "state": ("state", "status", "commission_state", "trang_thai"),
    "occurred_at": ("occurred_at", "date", "created_at", "transaction_date", "conversion_date", "ngay"),
    "subid": ("subid", "sub_id", "subid1", "click_ref", "affiliate_subid", "click_id"),
    "gclid": ("gclid", "google_click_id"),
    "order_value": ("order_value", "sale_amount", "revenue", "order_amount", "gia_tri_don"),
}

STATE_ALIASES = {
    "pending": CommissionState.PENDING,
    "cho duyet": CommissionState.PENDING,
    "cho_duyet": CommissionState.PENDING,
    "approved": CommissionState.APPROVED,
    "accepted": CommissionState.APPROVED,
    "duyet": CommissionState.APPROVED,
    "locked": CommissionState.LOCKED,
    "confirmed": CommissionState.LOCKED,
    "paid": CommissionState.PAID,
    "da tra": CommissionState.PAID,
    "da_tra": CommissionState.PAID,
    "rejected": CommissionState.REJECTED,
    "declined": CommissionState.REJECTED,
    "tu choi": CommissionState.REJECTED,
    "tu_choi": CommissionState.REJECTED,
    "refunded": CommissionState.REFUNDED,
    "refund": CommissionState.REFUNDED,
    "hoan": CommissionState.REFUNDED,
    "chargeback": CommissionState.CHARGEBACK,
    "reversed": CommissionState.CHARGEBACK,
}


def normalize_key(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def decode_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đọc được encoding của file CSV")


def detect_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {sep: sample.count(sep) for sep in (",", ";", "\t", "|")}
        return max(counts, key=counts.get)


def parse_decimal(value: str, field: str) -> Decimal:
    raw = value.strip().replace("\u00a0", "").replace(" ", "")
    raw = re.sub(r"[^0-9,.-]", "", raw)
    if not raw:
        raise ValueError(f"{field} bị trống")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", ".") if len(tail) in {1, 2} else raw.replace(",", "")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{field} không phải số hợp lệ: {value}") from exc
    if result < 0:
        raise ValueError(f"{field} không được âm")
    return result


def parse_datetime(value: str | None) -> datetime:
    if not value or not value.strip():
        return datetime.now(timezone.utc)
    raw = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(raw)
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Ngày không hợp lệ: {value}")


def parse_state(value: str | None) -> CommissionState:
    if not value or not value.strip():
        return CommissionState.PENDING
    normalized = normalize_key(value).replace("_", " ")
    direct = normalize_key(value).upper()
    if direct in CommissionState.__members__:
        return CommissionState[direct]
    if normalized in STATE_ALIASES:
        return STATE_ALIASES[normalized]
    normalized_underscore = normalized.replace(" ", "_")
    if normalized_underscore in STATE_ALIASES:
        return STATE_ALIASES[normalized_underscore]
    raise ValueError(f"Trạng thái không hỗ trợ: {value}")


def header_map(fieldnames: list[str]) -> dict[str, str | None]:
    normalized = {normalize_key(name): name for name in fieldnames if name}
    result: dict[str, str | None] = {}
    for target, aliases in ALIASES.items():
        result[target] = next((normalized[a] for a in aliases if a in normalized), None)
    return result


def _cell(row: dict[str, str], mapping: dict[str, str | None], key: str) -> str:
    source_key = mapping.get(key)
    return (row.get(source_key, "") if source_key else "").strip()


def parse_rows(data: bytes, source: str) -> tuple[list[ParsedCommission], list[dict[str, Any]], int]:
    text = decode_csv(data)
    delimiter = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV không có hàng tiêu đề")
    mapping = header_map(list(reader.fieldnames))
    missing = [name for name in ("external_id", "amount") if mapping[name] is None]
    if missing:
        raise ValueError(
            "Thiếu cột bắt buộc: " + ", ".join(missing) + ". Cần ID giao dịch và số hoa hồng."
        )

    parsed: list[ParsedCommission] = []
    errors: list[dict[str, Any]] = []
    rows_read = 0
    normalized_source = normalize_key(source).upper() or "CSV"
    for row_number, row in enumerate(reader, start=2):
        rows_read += 1
        try:
            raw_external_id = _cell(row, mapping, "external_id")
            if not raw_external_id:
                raise ValueError("ID giao dịch bị trống")
            amount = parse_decimal(_cell(row, mapping, "amount"), "amount")
            currency = (_cell(row, mapping, "currency") or "USD").upper()[:3]
            state = parse_state(_cell(row, mapping, "state"))
            occurred_at = parse_datetime(_cell(row, mapping, "occurred_at"))
            subid = _cell(row, mapping, "subid") or None
            gclid = _cell(row, mapping, "gclid") or None
            click_ref = subid or gclid
            click_ref_type = "SUBID" if subid else ("GCLID" if gclid else None)
            order_raw = _cell(row, mapping, "order_value")
            order_value = parse_decimal(order_raw, "order_value") if order_raw else None
            external_id = f"{normalized_source}:{raw_external_id}"
            canonical = "|".join(
                [external_id, str(amount), currency, state.value, occurred_at.isoformat(), click_ref or ""]
            )
            parsed.append(
                ParsedCommission(
                    raw_external_id=raw_external_id,
                    external_id=external_id,
                    amount=amount,
                    currency=currency,
                    state=state,
                    occurred_at=occurred_at,
                    source=normalized_source,
                    click_ref=click_ref,
                    click_ref_type=click_ref_type,
                    order_value=order_value,
                    raw_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                )
            )
        except ValueError as exc:
            errors.append({"row": row_number, "message": str(exc)})
    return parsed, errors, rows_read


def analyze_import(db: Session, data: bytes, source: str) -> dict[str, Any]:
    parsed, errors, rows_read = parse_rows(data, source)
    seen: dict[str, ParsedCommission] = {}
    unique_rows: list[ParsedCommission] = []
    duplicate_rows: list[ParsedCommission] = []
    file_conflicts: list[tuple[ParsedCommission, ParsedCommission]] = []
    for item in parsed:
        first = seen.get(item.external_id)
        if first is not None:
            if first.raw_hash == item.raw_hash:
                duplicate_rows.append(item)
            else:
                file_conflicts.append((first, item))
            continue
        seen[item.external_id] = item
        unique_rows.append(item)

    existing_items = list(
        db.scalars(select(Commission).where(Commission.external_id.in_(list(seen)))).all()
    ) if seen else []
    existing_map = {item.external_id: item for item in existing_items}
    new_rows: list[ParsedCommission] = []
    update_rows: list[ParsedCommission] = []
    conflict_rows: list[tuple[Commission, ParsedCommission]] = []
    duplicates_existing = 0
    for item in unique_rows:
        current = existing_map.get(item.external_id)
        if current is None:
            new_rows.append(item)
            continue
        immutable_same = (
            Decimal(current.amount) == item.amount
            and current.currency == item.currency
            and current.occurred_at.date() == item.occurred_at.date()
        )
        if not immutable_same:
            conflict_rows.append((current, item))
        elif current.state == item.state:
            duplicates_existing += 1
        else:
            update_rows.append(item)
    importable_rows = new_rows + update_rows

    subids = [item.click_ref for item in importable_rows if item.click_ref_type == "SUBID" and item.click_ref]
    gclids = [item.click_ref for item in importable_rows if item.click_ref_type == "GCLID" and item.click_ref]
    click_refs: set[str] = set()
    if subids or gclids:
        conditions = []
        if subids:
            conditions.append(Click.affiliate_subid.in_(subids))
        if gclids:
            conditions.append(Click.gclid.in_(gclids))
        clicks = db.scalars(select(Click).where(or_(*conditions))).all()
        click_refs.update(item.affiliate_subid for item in clicks if item.affiliate_subid)
        click_refs.update(item.gclid for item in clicks if item.gclid)

    totals_by_state: defaultdict[str, Decimal] = defaultdict(Decimal)
    totals_by_currency: defaultdict[str, Decimal] = defaultdict(Decimal)
    attributable = 0
    for item in importable_rows:
        totals_by_state[item.state.value] += item.amount
        totals_by_currency[item.currency] += item.amount
        if item.click_ref and item.click_ref in click_refs:
            attributable += 1

    return {
        "source": normalize_key(source).upper() or "CSV",
        "rows_read": rows_read,
        "valid_rows": len(importable_rows),
        "duplicates_existing": duplicates_existing,
        "updates_existing": len(update_rows),
        "duplicates_in_file": len(duplicate_rows),
        "conflict_count": len(file_conflicts) + len(conflict_rows),
        "error_count": len(errors),
        "errors": errors[:20],
        "totals_by_state": {key: str(value) for key, value in sorted(totals_by_state.items())},
        "totals_by_currency": {key: str(value) for key, value in sorted(totals_by_currency.items())},
        "attributable_rows": attributable,
        "unattributed_rows": len(importable_rows) - attributable,
        "_new_rows": new_rows,
        "_update_rows": update_rows,
        "_duplicate_rows": duplicate_rows,
        "_file_conflicts": file_conflicts,
        "_conflict_rows": conflict_rows,
    }


def _payload(item: ParsedCommission) -> dict[str, str]:
    return {
        "external_id": item.external_id,
        "amount": str(item.amount),
        "currency": item.currency,
        "state": item.state.value,
        "occurred_at": item.occurred_at.isoformat(),
        "raw_hash": item.raw_hash,
    }


def commit_import(db: Session, analysis: dict[str, Any], program_id: int | None = None) -> int:
    new_rows: list[ParsedCommission] = analysis["_new_rows"]
    update_rows: list[ParsedCommission] = analysis["_update_rows"]
    rows = new_rows + update_rows
    duplicate_rows: list[ParsedCommission] = analysis["_duplicate_rows"]
    file_conflicts: list[tuple[ParsedCommission, ParsedCommission]] = analysis[
        "_file_conflicts"
    ]
    conflict_rows: list[tuple[Commission, ParsedCommission]] = analysis["_conflict_rows"]

    subids = [item.click_ref for item in rows if item.click_ref_type == "SUBID" and item.click_ref]
    gclids = [item.click_ref for item in rows if item.click_ref_type == "GCLID" and item.click_ref]
    click_by_ref: dict[str, Click] = {}
    conditions = []
    if subids:
        conditions.append(Click.affiliate_subid.in_(subids))
    if gclids:
        conditions.append(Click.gclid.in_(gclids))
    if conditions:
        for click in db.scalars(select(Click).where(or_(*conditions))).all():
            if click.affiliate_subid:
                click_by_ref[click.affiliate_subid] = click
            if click.gclid:
                click_by_ref[click.gclid] = click

    written = 0
    update_ids = {item.external_id for item in update_rows}
    existing_commissions = {
        item.external_id: item
        for item in db.scalars(
            select(Commission)
            .where(Commission.external_id.in_(list(update_ids)))
        ).all()
    } if update_ids else {}

    for item in rows:
        click = click_by_ref.get(item.click_ref or "")
        if item.external_id in existing_commissions:
            commission = existing_commissions[item.external_id]
            commission.amount = item.amount
            commission.currency = item.currency
            commission.state = item.state
            commission.occurred_at = item.occurred_at
            commission.source = item.source
            if commission.conversion is not None:
                commission.conversion.click_id = click.id if click else commission.conversion.click_id
                commission.conversion.program_id = program_id or commission.conversion.program_id
                commission.conversion.order_value = item.order_value or commission.conversion.order_value
                commission.conversion.quality = (
                    DataQuality.MATCHED if commission.conversion.click_id else DataQuality.UNKNOWN
                )
            commission.quality = DataQuality.MATCHED if click else commission.quality
            db.flush()
            sync_commission_reconciliation(db, commission)
            written += 1
            continue

        conversion_external = f"{item.source}:CONVERSION:{item.raw_external_id}"
        conversion = Conversion(
            external_id=conversion_external,
            click_id=click.id if click else None,
            program_id=program_id,
            occurred_at=item.occurred_at,
            order_value=item.order_value,
            currency=item.currency,
            status="CONVERTED_PENDING",
            source=item.source,
            raw_hash=item.raw_hash,
            quality=DataQuality.MATCHED if click else DataQuality.UNKNOWN,
        )
        db.add(conversion)
        db.flush()
        commission = Commission(
            external_id=item.external_id,
            conversion_id=conversion.id,
            amount=item.amount,
            currency=item.currency,
            state=item.state,
            occurred_at=item.occurred_at,
            source=item.source,
            quality=DataQuality.MATCHED if click else DataQuality.OBSERVED,
        )
        db.add(commission)
        db.flush()
        sync_commission_reconciliation(db, commission)
        written += 1

    for item in duplicate_rows:
        record_duplicate(
            db,
            source=item.source,
            external_id=item.external_id,
            raw_hash=item.raw_hash,
        )
    for first, incoming in file_conflicts:
        record_import_conflict(
            db,
            source=incoming.source,
            external_id=incoming.external_id,
            first=_payload(first),
            incoming=_payload(incoming),
        )
    for commission, incoming in conflict_rows:
        record_conflict(db, commission=commission, incoming=_payload(incoming))

    apply_currency_normalization(db)
    db.commit()
    return written
