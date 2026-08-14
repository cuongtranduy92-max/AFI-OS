from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from afi_os.db import get_db
from afi_os.enums import ReconciliationStatus
from afi_os.models import (
    Campaign,
    Click,
    Commission,
    Conversion,
    FxRate,
    Project,
    ReconciliationItem,
    Spend,
)
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
    TrueProfitExpectedPayment,
    TrueProfitProjectRead,
    TrueProfitSummaryResponse,
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
from afi_os.services.true_profit import (
    CommissionRow,
    SpendRow,
    portfolio_summary,
    project_pnl,
)

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


def _usd_amount(item: Commission | Spend) -> Decimal | None:
    if item.currency.upper() == "USD":
        return Decimal(item.amount)
    if item.normalized_currency and item.normalized_currency.upper() == "USD":
        return Decimal(item.normalized_amount) if item.normalized_amount is not None else None
    return None


def _payout_days(project: Project) -> int | None:
    snapshots = [
        item
        for item in project.metric_snapshots
        if item.metric_key == "payout_timing_days" and item.numeric_value is not None
    ]
    if not snapshots:
        return None
    latest = max(snapshots, key=lambda item: (item.observed_at, item.id))
    return max(0, int(latest.numeric_value))


@router.get("/true-profit", response_model=TrueProfitSummaryResponse)
def true_profit_summary(db: Session = Depends(get_db)) -> TrueProfitSummaryResponse:
    """Cash-basis P&L: only PAID commission is money actually received."""
    projects = db.scalars(
        select(Project)
        .options(joinedload(Project.metric_snapshots))
        .order_by(Project.id)
    ).unique().all()
    project_by_id = {item.id: item for item in projects}
    projects_by_program: defaultdict[int, list[Project]] = defaultdict(list)
    for project in projects:
        if project.program_id is not None:
            projects_by_program[project.program_id].append(project)

    commissions_by_project: defaultdict[int, list[CommissionRow]] = defaultdict(list)
    spends_by_project: defaultdict[int, list[SpendRow]] = defaultdict(list)
    excluded_non_usd = 0
    unattributed = 0

    commissions = db.scalars(
        select(Commission)
        .options(
            joinedload(Commission.conversion)
            .joinedload(Conversion.click)
            .joinedload(Click.campaign)
        )
        .order_by(Commission.occurred_at, Commission.id)
    ).unique().all()
    for item in commissions:
        state = item.state.value if hasattr(item.state, "value") else str(item.state)
        if state not in {"PENDING", "APPROVED", "LOCKED", "PAID"}:
            continue
        amount = _usd_amount(item)
        if amount is None:
            excluded_non_usd += 1
            continue
        conversion = item.conversion
        project_id = None
        if conversion and conversion.click and conversion.click.campaign:
            project_id = conversion.click.campaign.project_id
        if project_id is None and conversion and conversion.program_id is not None:
            candidates = projects_by_program.get(conversion.program_id, [])
            # A shared Program is not enough to choose truthfully between projects.
            project_id = candidates[0].id if len(candidates) == 1 else None
        if project_id is None or project_id not in project_by_id:
            unattributed += 1
            continue
        project = project_by_id[project_id]
        commissions_by_project[project_id].append(
            CommissionRow(
                project_id=project_id,
                amount_usd=amount,
                state=state,
                converted_on=item.occurred_at.date(),
                clear_days=_payout_days(project),
                paid_on=item.paid_at.date() if item.paid_at else None,
            )
        )

    spends = db.scalars(
        select(Spend)
        .options(joinedload(Spend.campaign).joinedload(Campaign.ads_account))
        .order_by(Spend.spend_date, Spend.id)
    ).unique().all()
    charged_accounts: set[tuple[int, int]] = set()
    for item in spends:
        project_id = item.campaign.project_id
        if project_id is None or project_id not in project_by_id:
            continue
        amount = _usd_amount(item)
        if amount is None:
            excluded_non_usd += 1
            continue
        account = item.campaign.ads_account
        account_key = (project_id, account.id)
        rent = Decimal("0")
        if account_key not in charged_accounts:
            rent = Decimal(account.rent_cost or 0)
            charged_accounts.add(account_key)
        spends_by_project[project_id].append(
            SpendRow(
                project_id=project_id,
                amount_usd=amount,
                account_rent_usd=rent,
                spend_fee_pct=Decimal(account.spend_fee_pct or 0),
            )
        )

    # An account rent remains a cost even when the imported period has no spend row yet.
    campaigns = db.scalars(
        select(Campaign)
        .options(joinedload(Campaign.ads_account))
        .where(Campaign.project_id.is_not(None))
    ).unique().all()
    for campaign in campaigns:
        if campaign.project_id not in project_by_id:
            continue
        account_key = (campaign.project_id, campaign.ads_account.id)
        if account_key in charged_accounts:
            continue
        charged_accounts.add(account_key)
        spends_by_project[campaign.project_id].append(
            SpendRow(
                project_id=campaign.project_id,
                amount_usd=Decimal("0"),
                account_rent_usd=Decimal(campaign.ads_account.rent_cost or 0),
                spend_fee_pct=Decimal(campaign.ads_account.spend_fee_pct or 0),
            )
        )

    relevant_ids = sorted(set(commissions_by_project) | set(spends_by_project))
    pnls = [
        project_pnl(
            project_id,
            commissions_by_project[project_id],
            spends_by_project[project_id],
            date.today(),
        )
        for project_id in relevant_ids
    ]
    summary = portfolio_summary(pnls)
    alerts = list(summary.alerts)
    if unattributed:
        alerts.append(
            f"{unattributed} hoa hồng chưa nối được với dự án; cần bổ sung program/subid."
        )
    if excluded_non_usd:
        alerts.append(
            f"{excluded_non_usd} dòng chưa có số USD nên chưa được đưa vào lời lãi thật."
        )
    rows = []
    for pnl in pnls:
        project = project_by_id[pnl.project_id]
        rows.append(
            TrueProfitProjectRead(
                project_id=pnl.project_id,
                project_name=project.brand_name,
                domain=project.domain,
                spend_usd=pnl.spend,
                variable_cost_usd=pnl.variable_cost,
                total_cost_usd=pnl.total_cost,
                on_web_usd=pnl.on_web,
                withdrawn_usd=pnl.withdrawn,
                real_profit_usd=pnl.real_profit,
                expected_payments=[
                    TrueProfitExpectedPayment(expected_on=eta, amount_usd=amount)
                    for eta, amount in pnl.expected_dates
                ],
                overdue_payments=[
                    TrueProfitExpectedPayment(expected_on=eta, amount_usd=amount)
                    for eta, amount in pnl.overdue
                ],
            )
        )
    rows.sort(key=lambda item: item.real_profit_usd, reverse=True)
    return TrueProfitSummaryResponse(
        total_spend_usd=summary.total_spend,
        total_variable_cost_usd=summary.total_variable,
        total_cost_usd=summary.total_spend + summary.total_variable,
        total_on_web_usd=summary.total_on_web,
        total_withdrawn_usd=summary.total_withdrawn,
        real_profit_usd=summary.real_profit,
        collection_rate=summary.collection_rate,
        projects_paid=summary.projects_paid,
        projects_with_earnings=summary.projects_with_earnings,
        projects=rows,
        alerts=alerts,
        excluded_non_usd_rows=excluded_non_usd,
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
