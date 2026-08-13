from dataclasses import dataclass
from decimal import Decimal

from afi_os.enums import CommissionState


@dataclass(frozen=True)
class CommissionAmount:
    state: CommissionState
    amount: Decimal
    approval_probability: Decimal = Decimal("0.80")


@dataclass(frozen=True)
class FinanceSummary:
    pending_nominal: Decimal
    forecast_revenue: Decimal
    recognized_revenue: Decimal
    cash_received: Decimal
    rejected_or_reversed: Decimal


def summarize_commissions(items: list[CommissionAmount]) -> FinanceSummary:
    pending = Decimal("0")
    forecast = Decimal("0")
    recognized = Decimal("0")
    cash = Decimal("0")
    reversed_amount = Decimal("0")

    for item in items:
        if item.amount < 0:
            raise ValueError("commission amount must be non-negative")
        if not Decimal("0") <= item.approval_probability <= Decimal("1"):
            raise ValueError("approval_probability must be between 0 and 1")

        if item.state == CommissionState.PENDING:
            pending += item.amount
            forecast += item.amount * item.approval_probability
        elif item.state in {CommissionState.APPROVED, CommissionState.LOCKED}:
            recognized += item.amount
        elif item.state == CommissionState.PAID:
            recognized += item.amount
            cash += item.amount
        elif item.state in {
            CommissionState.REJECTED,
            CommissionState.REFUNDED,
            CommissionState.CHARGEBACK,
        }:
            reversed_amount += item.amount

    q = Decimal("0.000001")
    return FinanceSummary(
        pending_nominal=pending.quantize(q),
        forecast_revenue=forecast.quantize(q),
        recognized_revenue=recognized.quantize(q),
        cash_received=cash.quantize(q),
        rejected_or_reversed=reversed_amount.quantize(q),
    )
