from dataclasses import dataclass
from decimal import Decimal

from afi_os.enums import CommissionType

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class EconomicsInput:
    price: Decimal
    commission_type: CommissionType
    commission_rate: Decimal | None = None
    commission_flat: Decimal | None = None
    recurring_months: int | None = None
    forecast_horizon_months: int = 24
    clicks_per_sale: Decimal | None = None
    outbound_click_rate: Decimal = ONE
    merchant_conversion_rate: Decimal = Decimal("0.03")
    approval_rate: Decimal = Decimal("0.85")
    refund_rate: Decimal = Decimal("0.05")
    monthly_churn_rate: Decimal = Decimal("0.08")
    target_margin: Decimal = Decimal("0.30")
    confidence_discount: Decimal = Decimal("0.80")


@dataclass(frozen=True)
class EconomicsResult:
    commission_per_period: Decimal
    expected_active_periods: Decimal
    expected_commission_ltv: Decimal
    sale_probability_per_ad_click: Decimal
    effective_clicks_per_sale: Decimal | None
    break_even_cpc: Decimal
    safe_cpc: Decimal
    assumptions: dict[str, str]


def _clamp_fraction(value: Decimal, name: str) -> Decimal:
    if value < ZERO or value > ONE:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _commission_per_period(data: EconomicsInput) -> Decimal:
    if data.commission_flat is not None:
        if data.commission_flat < ZERO:
            raise ValueError("commission_flat must be non-negative")
        return data.commission_flat
    if data.commission_rate is None:
        raise ValueError("commission_rate or commission_flat is required")
    _clamp_fraction(data.commission_rate, "commission_rate")
    if data.price < ZERO:
        raise ValueError("price must be non-negative")
    return data.price * data.commission_rate


def _expected_active_periods(data: EconomicsInput) -> Decimal:
    if data.commission_type == CommissionType.ONE_TIME:
        return ONE

    if data.commission_type == CommissionType.RECURRING_UNSPECIFIED:
        raise ValueError(
            "recurring duration is unresolved; resolve commission facts before economics"
        )

    if data.commission_type == CommissionType.RECURRING_LIMITED:
        if not data.recurring_months or data.recurring_months < 1:
            raise ValueError("recurring_months must be >= 1 for recurring-limited commission")
        periods = data.recurring_months
    elif data.commission_type == CommissionType.RECURRING_LIFETIME:
        periods = data.forecast_horizon_months
        if periods < 1:
            raise ValueError("forecast_horizon_months must be >= 1")
    else:
        periods = data.recurring_months or data.forecast_horizon_months

    churn = _clamp_fraction(data.monthly_churn_rate, "monthly_churn_rate")
    survival = ONE
    expected = ZERO
    for _ in range(periods):
        expected += survival
        survival *= ONE - churn
    return expected


def evaluate_economics(data: EconomicsInput) -> EconomicsResult:
    """Calculate expected commission LTV and safe CPC without treating forecasts as cash."""

    outbound = _clamp_fraction(data.outbound_click_rate, "outbound_click_rate")
    merchant_cr = _clamp_fraction(data.merchant_conversion_rate, "merchant_conversion_rate")
    approval = _clamp_fraction(data.approval_rate, "approval_rate")
    refund = _clamp_fraction(data.refund_rate, "refund_rate")
    target_margin = _clamp_fraction(data.target_margin, "target_margin")
    confidence = _clamp_fraction(data.confidence_discount, "confidence_discount")

    commission = _commission_per_period(data)
    periods = _expected_active_periods(data)
    commission_ltv = commission * periods * approval * (ONE - refund)

    if data.clicks_per_sale is not None:
        if data.clicks_per_sale <= ZERO:
            raise ValueError("clicks_per_sale must be greater than 0")
        sale_probability = ONE / data.clicks_per_sale
        effective_clicks_per_sale = data.clicks_per_sale
        conversion_basis = "CLICKS_PER_SALE"
    else:
        sale_probability = outbound * merchant_cr
        effective_clicks_per_sale = ONE / sale_probability if sale_probability > ZERO else None
        conversion_basis = "FUNNEL_RATES"

    break_even_cpc = commission_ltv * sale_probability
    safe_cpc = break_even_cpc * (ONE - target_margin) * confidence

    return EconomicsResult(
        commission_per_period=commission.quantize(Decimal("0.000001")),
        expected_active_periods=periods.quantize(Decimal("0.000001")),
        expected_commission_ltv=commission_ltv.quantize(Decimal("0.000001")),
        sale_probability_per_ad_click=sale_probability.quantize(Decimal("0.000001")),
        effective_clicks_per_sale=(
            effective_clicks_per_sale.quantize(Decimal("0.000001"))
            if effective_clicks_per_sale is not None
            else None
        ),
        break_even_cpc=break_even_cpc.quantize(Decimal("0.000001")),
        safe_cpc=safe_cpc.quantize(Decimal("0.000001")),
        assumptions={
            "commission_type": data.commission_type.value,
            "conversion_basis": conversion_basis,
            "clicks_per_sale": str(data.clicks_per_sale or ""),
            "outbound_click_rate": str(outbound),
            "merchant_conversion_rate": str(merchant_cr),
            "forecast_horizon_months": str(data.forecast_horizon_months),
            "recurring_months": str(data.recurring_months or ""),
            "approval_rate": str(approval),
            "refund_rate": str(refund),
            "monthly_churn_rate": str(data.monthly_churn_rate),
            "target_margin": str(target_margin),
            "confidence_discount": str(confidence),
        },
    )
