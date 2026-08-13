from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from afi_os.enums import CommissionState, TermsWarningStatus
from afi_os.models import Campaign, CampaignProgramLink, Commission, Program
from afi_os.services.finance import CommissionAmount, summarize_commissions
from afi_os.services.programs import program_terms_status

ZERO = Decimal("0")


def terms_status_for_program(program: Program | None) -> str:
    if program is None:
        return TermsWarningStatus.WARNING_TERMS_UNVERIFIED.value
    return program_terms_status(program, list(program.terms_evidence))


def warning_level(status: str) -> str:
    if status == TermsWarningStatus.TERMS_OK.value:
        return "GREEN"
    if status in {
        TermsWarningStatus.WARNING_TERMS_CONFLICT.value,
        TermsWarningStatus.WARNING_TERMS_PROHIBITED.value,
    }:
        return "RED"
    return "AMBER"


def campaign_exposure_rows(db: Session) -> list[dict]:
    campaigns = list(
        db.scalars(
            select(Campaign)
            .options(
                joinedload(Campaign.ads_account),
                selectinload(Campaign.spends),
                selectinload(Campaign.daily_stats),
                joinedload(Campaign.program_link)
                .joinedload(CampaignProgramLink.program)
                .selectinload(Program.terms_evidence),
                joinedload(Campaign.program_link)
                .joinedload(CampaignProgramLink.program)
                .selectinload(Program.terms_research_runs),
            )
            .order_by(Campaign.name, Campaign.id)
        ).unique()
    )
    rows: list[dict] = []
    for campaign in campaigns:
        link = campaign.program_link
        program = link.program if link else None
        status = terms_status_for_program(program)
        spend_by_currency: defaultdict[str, Decimal] = defaultdict(Decimal)
        for item in campaign.spends:
            spend_by_currency[item.currency] += Decimal(item.amount)
        currency = campaign.currency
        spend = spend_by_currency.get(currency, ZERO)
        if not spend and spend_by_currency:
            currency, spend = sorted(spend_by_currency.items())[0]
        clicks = sum(item.clicks for item in campaign.daily_stats)
        impressions = sum(item.impressions for item in campaign.daily_stats)
        conversions = sum((Decimal(item.conversions) for item in campaign.daily_stats), ZERO)
        rows.append(
            {
                "campaign_id": campaign.id,
                "account_external_id": campaign.ads_account.external_id,
                "account_name": campaign.ads_account.name,
                "campaign_external_id": campaign.external_id,
                "campaign_name": campaign.name,
                "campaign_status": campaign.status,
                "channel_type": campaign.channel_type,
                "program_id": program.id if program else None,
                "program_name": program.name if program else None,
                "merchant_domain": program.merchant.website_domain if program else None,
                "terms_warning_status": status,
                "warning_level": warning_level(status),
                "project_included": True,
                "risk_acknowledged": bool(link and link.risk_acknowledged_at),
                "risk_acknowledged_at": link.risk_acknowledged_at if link else None,
                "risk_acknowledged_by": link.risk_acknowledged_by if link else None,
                "currency": currency,
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "average_cpc": spend / clicks if clicks else None,
            }
        )
    return rows


def exposure_summary(db: Session) -> dict:
    campaigns = campaign_exposure_rows(db)
    totals: defaultdict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "total_spend": ZERO,
            "spend_at_risk": ZERO,
            "pending_commission_at_risk": ZERO,
            "recognized_revenue": ZERO,
            "cash_received": ZERO,
        }
    )
    for row in campaigns:
        item = totals[row["currency"]]
        item["total_spend"] += row["spend"]
        if row["terms_warning_status"] != TermsWarningStatus.TERMS_OK.value:
            item["spend_at_risk"] += row["spend"]

    programs = {
        item.id: item
        for item in db.scalars(
            select(Program).options(
                selectinload(Program.terms_evidence),
                selectinload(Program.terms_research_runs),
            )
        ).all()
    }
    commissions = list(
        db.scalars(select(Commission).options(joinedload(Commission.conversion))).all()
    )
    grouped: defaultdict[str, list[Commission]] = defaultdict(list)
    for commission in commissions:
        grouped[commission.currency].append(commission)
        conversion = commission.conversion
        program = programs.get(conversion.program_id) if conversion else None
        risky = terms_status_for_program(program) != TermsWarningStatus.TERMS_OK.value
        if risky and commission.state in {
            CommissionState.PENDING,
            CommissionState.APPROVED,
            CommissionState.LOCKED,
        }:
            totals[commission.currency]["pending_commission_at_risk"] += Decimal(
                commission.amount
            )

    for currency, items in grouped.items():
        finance = summarize_commissions(
            [CommissionAmount(state=item.state, amount=Decimal(item.amount)) for item in items]
        )
        totals[currency]["recognized_revenue"] = finance.recognized_revenue
        totals[currency]["cash_received"] = finance.cash_received

    currency_rows = []
    for currency, item in sorted(totals.items()):
        currency_rows.append(
            {
                "currency": currency,
                **item,
                "actual_net_cash": item["cash_received"] - item["total_spend"],
            }
        )
    return {
        "currencies": currency_rows,
        "campaign_count": len(campaigns),
        "active_campaign_count": sum(
            row["campaign_status"].upper() in {"ENABLED", "ACTIVE"} for row in campaigns
        ),
        "warning_campaign_count": sum(
            row["terms_warning_status"] != TermsWarningStatus.TERMS_OK.value
            for row in campaigns
        ),
        "acknowledged_warning_count": sum(
            row["terms_warning_status"] != TermsWarningStatus.TERMS_OK.value
            and row["risk_acknowledged"]
            for row in campaigns
        ),
        "campaigns": campaigns,
    }
