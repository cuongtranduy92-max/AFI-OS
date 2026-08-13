from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, ReconciliationStatus
from afi_os.models import AuditLog, Commission, ReconciliationItem


def _dedupe_key(*parts: str) -> str:
    canonical = "|".join(str(part) for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _upsert_item(
    db: Session,
    *,
    key: str,
    status: ReconciliationStatus,
    entity_type: str,
    entity_id: str | None,
    reason: str,
    payload: dict[str, Any],
    auto_resolve: bool = False,
) -> ReconciliationItem:
    item = db.scalar(select(ReconciliationItem).where(ReconciliationItem.dedupe_key == key))
    if item is None:
        item = ReconciliationItem(
            status=status,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_key=key,
            reason=reason,
            payload_json=payload,
        )
        db.add(item)
    else:
        status_changed = item.status != status
        item.status = status
        item.entity_id = entity_id
        item.reason = reason
        item.payload_json = payload
        if status_changed:
            item.resolved_at = None
            item.resolved_by = None
            item.resolution_note = None
    if auto_resolve and item.resolved_at is None:
        item.resolved_at = datetime.now(UTC)
        item.resolved_by = "system"
        item.resolution_note = "Attribution đầy đủ; không cần xử lý."
    return item


def sync_commission_reconciliation(db: Session, commission: Commission) -> ReconciliationItem:
    conversion = commission.conversion
    has_click = bool(conversion and conversion.click_id)
    has_program = bool(conversion and conversion.program_id)
    if has_click and has_program:
        status = ReconciliationStatus.ATTRIBUTED
        reason = "Đã nối commission với click và chương trình."
    elif has_click or has_program:
        status = ReconciliationStatus.PARTIAL
        reason = (
            "Đã có click nhưng thiếu chương trình."
            if has_click
            else "Đã có chương trình nhưng chưa nối được click/SubID."
        )
    else:
        status = ReconciliationStatus.UNATTRIBUTED
        reason = "Chưa có click/SubID và chưa gắn chương trình."
    return _upsert_item(
        db,
        key=f"COMMISSION_ATTRIBUTION:{commission.id}",
        status=status,
        entity_type="COMMISSION",
        entity_id=str(commission.id),
        reason=reason,
        payload={
            "external_id": commission.external_id,
            "has_click": has_click,
            "has_program": has_program,
            "currency": commission.currency,
            "amount": str(commission.amount),
        },
        auto_resolve=status == ReconciliationStatus.ATTRIBUTED,
    )


def record_duplicate(
    db: Session,
    *,
    source: str,
    external_id: str,
    raw_hash: str,
) -> ReconciliationItem:
    return _upsert_item(
        db,
        key=_dedupe_key("COMMISSION_DUPLICATE", source, external_id, raw_hash),
        status=ReconciliationStatus.DUPLICATE,
        entity_type="COMMISSION_IMPORT",
        entity_id=external_id,
        reason="File có nhiều dòng cùng ID giao dịch; chỉ giữ dòng đầu tiên.",
        payload={"source": source, "external_id": external_id, "raw_hash": raw_hash},
    )


def record_conflict(
    db: Session,
    *,
    commission: Commission,
    incoming: dict[str, str],
) -> ReconciliationItem:
    return _upsert_item(
        db,
        key=_dedupe_key("COMMISSION_CONFLICT", str(commission.id), incoming["raw_hash"]),
        status=ReconciliationStatus.CONFLICT,
        entity_type="COMMISSION",
        entity_id=str(commission.id),
        reason="Cùng ID giao dịch nhưng số tiền, tiền tệ hoặc ngày giao dịch khác.",
        payload={
            "external_id": commission.external_id,
            "existing": {
                "amount": str(commission.amount),
                "currency": commission.currency,
                "occurred_at": commission.occurred_at.isoformat(),
                "state": commission.state.value,
            },
            "incoming": incoming,
        },
    )


def record_import_conflict(
    db: Session,
    *,
    source: str,
    external_id: str,
    first: dict[str, str],
    incoming: dict[str, str],
) -> ReconciliationItem:
    return _upsert_item(
        db,
        key=_dedupe_key(
            "COMMISSION_IMPORT_CONFLICT",
            source,
            external_id,
            first["raw_hash"],
            incoming["raw_hash"],
        ),
        status=ReconciliationStatus.CONFLICT,
        entity_type="COMMISSION_IMPORT",
        entity_id=external_id,
        reason="Trong cùng file có một ID giao dịch nhưng dữ liệu tài chính khác nhau.",
        payload={
            "source": source,
            "external_id": external_id,
            "first": first,
            "incoming": incoming,
        },
    )


def resolve_item(
    db: Session,
    item: ReconciliationItem,
    *,
    resolved_by: str,
    note: str,
) -> ReconciliationItem:
    item.resolved_at = datetime.now(UTC)
    item.resolved_by = resolved_by.strip() or "operator"
    item.resolution_note = note.strip()
    db.add(
        AuditLog(
            entity_type="reconciliation_item",
            entity_id=str(item.id),
            action=AuditAction.APPROVE,
            actor=item.resolved_by,
            payload_json={"status": item.status.value, "note": item.resolution_note},
        )
    )
    db.commit()
    db.refresh(item)
    return item


def reconciliation_summary(db: Session, *, include_resolved: bool = True) -> dict:
    statement = select(ReconciliationItem).order_by(
        ReconciliationItem.resolved_at.is_not(None),
        ReconciliationItem.updated_at.desc(),
        ReconciliationItem.id.desc(),
    )
    if not include_resolved:
        statement = statement.where(ReconciliationItem.resolved_at.is_(None))
    items = list(db.scalars(statement).all())
    all_items = list(db.scalars(select(ReconciliationItem)).all())
    current_attribution = [
        item
        for item in all_items
        if item.entity_type == "COMMISSION"
        and item.dedupe_key
        and item.payload_json.get("has_click") is not None
    ]
    status_counts = Counter(item.status.value for item in current_attribution)
    issue_counts = Counter(
        item.status.value
        for item in all_items
        if item.status in {ReconciliationStatus.DUPLICATE, ReconciliationStatus.CONFLICT}
        and item.resolved_at is None
    )
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "open_issue_counts": dict(sorted(issue_counts.items())),
        "open_items": sum(item.resolved_at is None for item in all_items),
        "items": items,
    }
