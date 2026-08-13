from decimal import Decimal

from afi_os.enums import CommissionType
from afi_os.services.economics import EconomicsInput, evaluate_economics


def test_one_time_economics() -> None:
    result = evaluate_economics(
        EconomicsInput(
            price=Decimal("100"),
            commission_type=CommissionType.ONE_TIME,
            commission_rate=Decimal("0.30"),
            outbound_click_rate=Decimal("1"),
            merchant_conversion_rate=Decimal("0.04"),
            approval_rate=Decimal("0.80"),
            refund_rate=Decimal("0"),
            target_margin=Decimal("0.25"),
            confidence_discount=Decimal("0.80"),
        )
    )
    assert result.commission_per_period == Decimal("30.000000")
    assert result.expected_commission_ltv == Decimal("24.000000")
    assert result.break_even_cpc == Decimal("0.960000")
    assert result.safe_cpc == Decimal("0.576000")


def test_recurring_lifetime_uses_horizon_and_churn() -> None:
    result = evaluate_economics(
        EconomicsInput(
            price=Decimal("50"),
            commission_type=CommissionType.RECURRING_LIFETIME,
            commission_rate=Decimal("0.30"),
            forecast_horizon_months=24,
            monthly_churn_rate=Decimal("0.10"),
        )
    )
    assert result.expected_active_periods > Decimal("8")
    assert result.expected_active_periods < Decimal("10")
    assert result.expected_commission_ltv > Decimal("100")


def test_course_baseline_150_clicks_per_sale() -> None:
    result = evaluate_economics(
        EconomicsInput(
            price=Decimal("49"),
            commission_type=CommissionType.ONE_TIME,
            commission_rate=Decimal("0.30"),
            clicks_per_sale=Decimal("150"),
            approval_rate=Decimal("0.85"),
            refund_rate=Decimal("0.05"),
            target_margin=Decimal("0.30"),
            confidence_discount=Decimal("0.80"),
        )
    )
    assert result.sale_probability_per_ad_click == Decimal("0.006667")
    assert result.effective_clicks_per_sale == Decimal("150.000000")
    assert result.break_even_cpc == Decimal("0.079135")
    assert result.safe_cpc == Decimal("0.044316")
