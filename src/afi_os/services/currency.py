from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, FxRateReviewStatus
from afi_os.models import AuditLog, Commission, FinanceSettings, FxRate, Spend
from afi_os.services.finance import CommissionAmount, summarize_commissions

MIN_ACCEPT_CONFIDENCE = Decimal("0.8000")
AMOUNT_QUANTUM = Decimal("0.000001")
RATE_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True)
class AppliedRate:
    rate: Decimal
    record: FxRate | None
    source: str


def normalize_currency_code(value: str) -> str:
    code = (value or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("Mã tiền tệ phải gồm đúng 3 chữ cái, ví dụ USD hoặc VND")
    return code


def finance_settings(db: Session) -> FinanceSettings:
    settings = db.get(FinanceSettings, 1)
    if settings is None:
        settings = FinanceSettings(id=1, base_currency="VND", max_rate_age_days=7)
        db.add(settings)
        db.flush()
    return settings


def update_finance_settings(
    db: Session,
    *,
    base_currency: str,
    max_rate_age_days: int,
    actor: str,
) -> tuple[FinanceSettings, dict]:
    if not 0 <= max_rate_age_days <= 31:
        raise ValueError("Tuổi tối đa của tỷ giá phải từ 0 đến 31 ngày")
    settings = finance_settings(db)
    previous = {
        "base_currency": settings.base_currency,
        "max_rate_age_days": settings.max_rate_age_days,
    }
    settings.base_currency = normalize_currency_code(base_currency)
    settings.max_rate_age_days = max_rate_age_days
    result = apply_currency_normalization(db)
    db.add(
        AuditLog(
            entity_type="finance_settings",
            entity_id="1",
            action=AuditAction.UPDATE,
            actor=actor,
            payload_json={"before": previous, "after": result["settings"]},
        )
    )
    db.commit()
    db.refresh(settings)
    return settings, result


def _rate_hash(
    rate_date: date,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
    source_name: str,
    source_url: str,
) -> str:
    canonical = "|".join(
        (
            rate_date.isoformat(),
            from_currency,
            to_currency,
            str(rate.normalize()),
            source_name.strip(),
            source_url.strip(),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_fx_rate_proposal(
    db: Session,
    *,
    rate_date: date,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
    source_name: str,
    source_url: str,
    checked_at: datetime,
    confidence: Decimal,
    actor: str,
) -> tuple[FxRate, bool]:
    from_code = normalize_currency_code(from_currency)
    to_code = normalize_currency_code(to_currency)
    if from_code == to_code:
        raise ValueError("Không cần nhập tỷ giá khi hai loại tiền giống nhau")
    if rate <= 0:
        raise ValueError("Tỷ giá phải lớn hơn 0")
    if not Decimal("0") <= confidence <= Decimal("1"):
        raise ValueError("Confidence phải nằm trong khoảng 0 đến 1")
    source_name = source_name.strip()
    source_url = source_url.strip()
    if not source_name:
        raise ValueError("Tên nguồn tỷ giá bị trống")
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("Tỷ giá phải có URL nguồn http(s)")
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)

    source_hash = _rate_hash(
        rate_date,
        from_code,
        to_code,
        rate,
        source_name,
        source_url,
    )
    existing = db.scalar(select(FxRate).where(FxRate.source_hash == source_hash))
    if existing is not None:
        if existing.review_status != FxRateReviewStatus.ACCEPTED:
            existing.checked_at = checked_at
            existing.confidence = confidence
            db.add(
                AuditLog(
                    entity_type="fx_rate",
                    entity_id=str(existing.id),
                    action=AuditAction.UPDATE,
                    actor=actor,
                    payload_json={
                        "confidence": str(confidence),
                        "checked_at": checked_at.isoformat(),
                        "review_status": existing.review_status.value,
                    },
                )
            )
            db.commit()
            db.refresh(existing)
        return existing, True

    item = FxRate(
        rate_date=rate_date,
        from_currency=from_code,
        to_currency=to_code,
        rate=rate.quantize(RATE_QUANTUM),
        source_name=source_name,
        source_url=source_url,
        checked_at=checked_at,
        confidence=confidence,
        review_status=FxRateReviewStatus.PROPOSED,
        source_hash=source_hash,
    )
    db.add(item)
    db.flush()
    db.add(
        AuditLog(
            entity_type="fx_rate",
            entity_id=str(item.id),
            action=AuditAction.CREATE,
            actor=actor,
            payload_json={
                "from": from_code,
                "to": to_code,
                "rate": str(item.rate),
                "rate_date": rate_date.isoformat(),
                "review_status": FxRateReviewStatus.PROPOSED.value,
            },
        )
    )
    db.commit()
    db.refresh(item)
    return item, False


def review_fx_rate(
    db: Session,
    item: FxRate,
    *,
    action: str,
    reviewed_by: str,
) -> dict:
    normalized_action = action.strip().upper()
    if normalized_action not in {"ACCEPT", "REJECT"}:
        raise ValueError("Action phải là ACCEPT hoặc REJECT")
    if normalized_action == "ACCEPT":
        if Decimal(item.confidence) < MIN_ACCEPT_CONFIDENCE:
            raise ValueError("Chỉ chấp nhận tỷ giá có confidence từ 0,8")
        conflicts = list(
            db.scalars(
                select(FxRate).where(
                    FxRate.id != item.id,
                    FxRate.rate_date == item.rate_date,
                    FxRate.from_currency == item.from_currency,
                    FxRate.to_currency == item.to_currency,
                    FxRate.review_status == FxRateReviewStatus.ACCEPTED,
                )
            ).all()
        )
        if any(Decimal(other.rate) != Decimal(item.rate) for other in conflicts):
            raise ValueError("Đã có tỷ giá ACCEPTED khác cho cùng cặp tiền và ngày")
        item.review_status = FxRateReviewStatus.ACCEPTED
        audit_action = AuditAction.APPROVE
    else:
        item.review_status = FxRateReviewStatus.REJECTED
        audit_action = AuditAction.BLOCK
    item.reviewed_at = datetime.now(UTC)
    item.reviewed_by = reviewed_by.strip() or "operator"
    db.flush()
    result = apply_currency_normalization(db)
    db.add(
        AuditLog(
            entity_type="fx_rate",
            entity_id=str(item.id),
            action=audit_action,
            actor=item.reviewed_by,
            payload_json={
                "review_status": item.review_status.value,
                "normalized_rows": result["normalized_rows"],
                "missing_rows": result["missing_rows"],
            },
        )
    )
    db.commit()
    db.refresh(item)
    return result


def _rate_for(
    db: Session,
    from_currency: str,
    to_currency: str,
    on_date: date,
    max_age_days: int,
) -> AppliedRate | None:
    if from_currency == to_currency:
        return AppliedRate(rate=Decimal("1"), record=None, source="IDENTITY")

    candidates = list(
        db.scalars(
            select(FxRate)
            .where(
                FxRate.review_status == FxRateReviewStatus.ACCEPTED,
                FxRate.rate_date <= on_date,
                or_(
                    (
                        (FxRate.from_currency == from_currency)
                        & (FxRate.to_currency == to_currency)
                    ),
                    (
                        (FxRate.from_currency == to_currency)
                        & (FxRate.to_currency == from_currency)
                    ),
                ),
            )
            .order_by(FxRate.rate_date.desc(), FxRate.id.desc())
        ).all()
    )
    for item in candidates:
        age = (on_date - item.rate_date).days
        if age > max_age_days:
            continue
        if item.from_currency == from_currency:
            rate = Decimal(item.rate)
        else:
            if Decimal(item.rate) == 0:
                continue
            rate = Decimal("1") / Decimal(item.rate)
        return AppliedRate(
            rate=rate.quantize(RATE_QUANTUM),
            record=item,
            source=item.source_name,
        )
    return None


def _clear_normalization(item: Spend | Commission) -> None:
    item.normalized_amount = None
    item.normalized_currency = None
    item.fx_rate = None
    item.fx_source = None
    item.fx_rate_id = None


def _apply_one(
    db: Session,
    item: Spend | Commission,
    *,
    on_date: date,
    settings: FinanceSettings,
) -> bool:
    source_currency = normalize_currency_code(item.currency)
    applied = _rate_for(
        db,
        source_currency,
        settings.base_currency,
        on_date,
        settings.max_rate_age_days,
    )
    if applied is None:
        _clear_normalization(item)
        return False
    item.normalized_amount = (Decimal(item.amount) * applied.rate).quantize(AMOUNT_QUANTUM)
    item.normalized_currency = settings.base_currency
    item.fx_rate = applied.rate
    item.fx_source = applied.source
    item.fx_rate_id = applied.record.id if applied.record else None
    return True


def apply_currency_normalization(db: Session) -> dict:
    settings = finance_settings(db)
    settings.base_currency = normalize_currency_code(settings.base_currency)
    spend_rows = list(db.scalars(select(Spend)).all())
    commission_rows = list(db.scalars(select(Commission)).all())
    normalized = 0
    missing = 0
    missing_pairs: defaultdict[str, int] = defaultdict(int)

    for item in spend_rows:
        if _apply_one(db, item, on_date=item.spend_date, settings=settings):
            normalized += 1
        else:
            missing += 1
            missing_pairs[f"{item.currency}->{settings.base_currency}"] += 1
    for item in commission_rows:
        if _apply_one(db, item, on_date=item.occurred_at.date(), settings=settings):
            normalized += 1
        else:
            missing += 1
            missing_pairs[f"{item.currency}->{settings.base_currency}"] += 1
    db.flush()
    return {
        "settings": {
            "base_currency": settings.base_currency,
            "max_rate_age_days": settings.max_rate_age_days,
        },
        "normalized_rows": normalized,
        "missing_rows": missing,
        "missing_pairs": dict(sorted(missing_pairs.items())),
    }


def normalization_summary(db: Session) -> dict:
    settings = finance_settings(db)
    spends = list(db.scalars(select(Spend)).all())
    commissions = list(db.scalars(select(Commission)).all())
    normalized_spend = sum(
        (
            Decimal(item.normalized_amount)
            for item in spends
            if item.normalized_currency == settings.base_currency
            and item.normalized_amount is not None
        ),
        Decimal("0"),
    )
    normalized_commissions = [
        CommissionAmount(state=item.state, amount=Decimal(item.normalized_amount))
        for item in commissions
        if item.normalized_currency == settings.base_currency
        and item.normalized_amount is not None
    ]
    finance = summarize_commissions(normalized_commissions)
    spend_missing = sum(
        item.normalized_currency != settings.base_currency or item.normalized_amount is None
        for item in spends
    )
    commission_missing = sum(
        item.normalized_currency != settings.base_currency or item.normalized_amount is None
        for item in commissions
    )
    missing_pairs: defaultdict[str, int] = defaultdict(int)
    for item in [*spends, *commissions]:
        if item.normalized_currency != settings.base_currency or item.normalized_amount is None:
            missing_pairs[f"{item.currency}->{settings.base_currency}"] += 1
    return {
        "base_currency": settings.base_currency,
        "max_rate_age_days": settings.max_rate_age_days,
        "normalized_spend": normalized_spend.quantize(AMOUNT_QUANTUM),
        "pending_nominal": finance.pending_nominal,
        "forecast_revenue": finance.forecast_revenue,
        "recognized_revenue": finance.recognized_revenue,
        "cash_received": finance.cash_received,
        "rejected_or_reversed": finance.rejected_or_reversed,
        "actual_net_cash": (finance.cash_received - normalized_spend).quantize(AMOUNT_QUANTUM),
        "spend_rows": len(spends),
        "spend_normalized": len(spends) - spend_missing,
        "spend_missing": spend_missing,
        "commission_rows": len(commissions),
        "commission_normalized": len(commissions) - commission_missing,
        "commission_missing": commission_missing,
        "missing_pairs": dict(sorted(missing_pairs.items())),
    }
