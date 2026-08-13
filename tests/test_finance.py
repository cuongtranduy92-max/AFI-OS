from decimal import Decimal

from afi_os.enums import CommissionState
from afi_os.services.finance import CommissionAmount, summarize_commissions


def test_pending_is_not_recognized_or_cash() -> None:
    summary = summarize_commissions(
        [
            CommissionAmount(CommissionState.PENDING, Decimal("100"), Decimal("0.70")),
            CommissionAmount(CommissionState.APPROVED, Decimal("40")),
            CommissionAmount(CommissionState.PAID, Decimal("25")),
            CommissionAmount(CommissionState.REJECTED, Decimal("10")),
        ]
    )
    assert summary.pending_nominal == Decimal("100.000000")
    assert summary.forecast_revenue == Decimal("70.000000")
    assert summary.recognized_revenue == Decimal("65.000000")
    assert summary.cash_received == Decimal("25.000000")
    assert summary.rejected_or_reversed == Decimal("10.000000")
