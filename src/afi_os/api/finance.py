from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from afi_os.db import get_db
from afi_os.enums import ReconciliationStatus
from afi_os.models import Commission, Conversion, FxRate, ReconciliationItem
from afi_os.schemas import (
    CommissionImportCommitResponse,
    CommissionImportPreview,
    CommissionRead,
    CurrencyNormalizationResult,
    CurrencyNormalizationSummary,
    FinanceCurrencySummary,
    FinanceSettingsRead,
    FinanceSettingsUpdate,
    FinanceSummaryResponse,
    FxRateCreate,
    FxRateProposalResponse,
    FxRateRead,
    FxRateReviewRequest,
    FxRateReviewResponse,
    ReconciliationResolveRequest,
    ReconciliationSummaryResponse,
)
from afi_os.services.commission_import import analyze_import, commit_import
from afi_os.services.currency import (
    apply_currency_normalization,
    create_fx_rate_proposal,
    finance_settings,
    normalization_summary,
    review_fx_rate,
    update_finance_settings,
)
from afi_os.services.finance import CommissionAmount, summarize_commissions
from afi_os.services.reconciliation import reconciliation_summary, resolve_item

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _public_analysis(data: dict) -> dict:
    return {key: value for key, value in data.items() if not key.startswith("_")}


@router.post("/commission-import/preview", response_model=CommissionImportPreview)
async def preview_commissions(
    file: UploadFile = File(...),
    source: str = Form(default="CSV"),
    db: Session = Depends(get_db),
) -> CommissionImportPreview:
    analysis = analyze_import(db, await file.read(), source)
    return CommissionImportPreview(**_public_analysis(analysis))


@router.post("/commission-import/commit", response_model=CommissionImportCommitResponse)
async def import_commissions(
    file: UploadFile = File(...),
    source: str = Form(default="CSV"),
    program_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> CommissionImportCommitResponse:
    analysis = analyze_import(db, await file.read(), source)
    written = commit_import(db, analysis, program_id=program_id)
    return CommissionImportCommitResponse(rows_written=written, **_public_analysis(analysis))


@router.get("/summary", response_model=FinanceSummaryResponse)
def finance_summary(db: Session = Depends(get_db)) -> FinanceSummaryResponse:
    commissions = db.scalars(
        select(Commission)
        .options(joinedload(Commission.conversion))
        .order_by(Commission.occurred_at.desc())
    ).all()
    grouped: defaultdict[str, list[Commission]] = defaultdict(list)
    for item in commissions:
        grouped[item.currency].append(item)

    result: list[FinanceCurrencySummary] = []
    total_unattributed = 0
    for currency, items in sorted(grouped.items()):
        summary = summarize_commissions(
            [CommissionAmount(state=item.state, amount=Decimal(item.amount)) for item in items]
        )
        unattributed = sum(
            1 for item in items if item.conversion is None or item.conversion.click_id is None
        )
        total_unattributed += unattributed
        result.append(
            FinanceCurrencySummary(
                currency=currency,
                pending_nominal=summary.pending_nominal,
                forecast_revenue=summary.forecast_revenue,
                recognized_revenue=summary.recognized_revenue,
                cash_received=summary.cash_received,
                rejected_or_reversed=summary.rejected_or_reversed,
                transaction_count=len(items),
                unattributed_count=unattributed,
            )
        )
    return FinanceSummaryResponse(
        currencies=result,
        total_transactions=len(commissions),
        total_unattributed=total_unattributed,
    )


@router.get("/settings", response_model=FinanceSettingsRead)
def get_finance_settings(db: Session = Depends(get_db)) -> FinanceSettingsRead:
    settings = finance_settings(db)
    return FinanceSettingsRead.model_validate(settings)


@router.patch("/settings", response_model=CurrencyNormalizationResult)
def patch_finance_settings(
    payload: FinanceSettingsUpdate,
    db: Session = Depends(get_db),
) -> CurrencyNormalizationResult:
    try:
        _, result = update_finance_settings(
            db,
            base_currency=payload.base_currency,
            max_rate_age_days=payload.max_rate_age_days,
            actor=payload.actor,
        )
    except ValueError as exc:
        raise _value_error(exc) from exc
    return CurrencyNormalizationResult(**result)


@router.post("/fx-rates", response_model=FxRateProposalResponse)
def propose_fx_rate(
    payload: FxRateCreate,
    db: Session = Depends(get_db),
) -> FxRateProposalResponse:
    try:
        item, duplicate = create_fx_rate_proposal(
            db,
            rate_date=payload.rate_date,
            from_currency=payload.from_currency,
            to_currency=payload.to_currency,
            rate=payload.rate,
            source_name=payload.source_name,
            source_url=payload.source_url,
            checked_at=payload.checked_at,
            confidence=payload.confidence,
            actor=payload.actor,
        )
    except ValueError as exc:
        raise _value_error(exc) from exc
    return FxRateProposalResponse(rate=FxRateRead.model_validate(item), duplicate=duplicate)


@router.get("/fx-rates", response_model=list[FxRateRead])
def list_fx_rates(db: Session = Depends(get_db)) -> list[FxRateRead]:
    items = db.scalars(select(FxRate).order_by(FxRate.rate_date.desc(), FxRate.id.desc())).all()
    return [FxRateRead.model_validate(item) for item in items]


@router.post("/fx-rates/{rate_id}/review", response_model=FxRateReviewResponse)
def review_rate(
    rate_id: int,
    payload: FxRateReviewRequest,
    db: Session = Depends(get_db),
) -> FxRateReviewResponse:
    item = db.get(FxRate, rate_id)
    if item is None:
        raise HTTPException(status_code=404, detail="FX rate not found")
    try:
        result = review_fx_rate(
            db,
            item,
            action=payload.action,
            reviewed_by=payload.reviewed_by,
        )
    except ValueError as exc:
        raise _value_error(exc) from exc
    return FxRateReviewResponse(
        rate=FxRateRead.model_validate(item),
        normalization=CurrencyNormalizationResult(**result),
    )


@router.post("/normalize", response_model=CurrencyNormalizationResult)
def normalize_finance(db: Session = Depends(get_db)) -> CurrencyNormalizationResult:
    result = apply_currency_normalization(db)
    db.commit()
    return CurrencyNormalizationResult(**result)


@router.get("/normalization", response_model=CurrencyNormalizationSummary)
def get_normalization_summary(db: Session = Depends(get_db)) -> CurrencyNormalizationSummary:
    return CurrencyNormalizationSummary(**normalization_summary(db))


@router.get("/reconciliation", response_model=ReconciliationSummaryResponse)
def get_reconciliation(
    include_resolved: bool = True,
    db: Session = Depends(get_db),
) -> ReconciliationSummaryResponse:
    return ReconciliationSummaryResponse(
        **reconciliation_summary(db, include_resolved=include_resolved)
    )


@router.post(
    "/reconciliation/{item_id}/resolve",
    response_model=ReconciliationSummaryResponse,
)
def resolve_reconciliation_item(
    item_id: int,
    payload: ReconciliationResolveRequest,
    db: Session = Depends(get_db),
) -> ReconciliationSummaryResponse:
    item = db.get(ReconciliationItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Reconciliation item not found")
    resolve_item(
        db,
        item,
        resolved_by=payload.resolved_by,
        note=payload.note,
    )
    return ReconciliationSummaryResponse(**reconciliation_summary(db))


@router.get("/commissions", response_model=list[CommissionRead])
def list_commissions(limit: int = 100, db: Session = Depends(get_db)) -> list[CommissionRead]:
    limit = max(1, min(limit, 500))
    rows = db.scalars(
        select(Commission)
        .options(joinedload(Commission.conversion).joinedload(Conversion.click))
        .order_by(Commission.occurred_at.desc(), Commission.id.desc())
        .limit(limit)
    ).all()
    output: list[CommissionRead] = []
    for item in rows:
        conversion = item.conversion
        click = conversion.click if conversion else None
        has_program = bool(conversion and conversion.program_id)
        if click is not None and has_program:
            reconciliation_status = ReconciliationStatus.ATTRIBUTED
        elif click is not None or has_program:
            reconciliation_status = ReconciliationStatus.PARTIAL
        else:
            reconciliation_status = ReconciliationStatus.UNATTRIBUTED
        output.append(
            CommissionRead(
                id=item.id,
                external_id=item.external_id,
                amount=item.amount,
                currency=item.currency,
                state=item.state,
                occurred_at=item.occurred_at,
                source=item.source,
                quality=item.quality,
                attributed=click is not None,
                click_reference=(click.affiliate_subid or click.gclid) if click else None,
                normalized_amount=item.normalized_amount,
                normalized_currency=item.normalized_currency,
                reconciliation_status=reconciliation_status,
            )
        )
    return output
