"""Trang 4 — Lời lãi THẬT + xử lý search volume dạng khoảng.

Nguyên tắc bất di bất dịch (buổi 3, 13, 15): **CHỈ TIN TIỀN VỀ TÚI**.
Tiền hiện trên dashboard NET = "tiền màn hình", KHÔNG phải lợi nhuận.
Lời lãi = tiền THỰC RÚT − chi ads − biến phí invoice (thuê acc + % spend).

Thuần deterministic, không chạm DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

D0 = Decimal("0")

# ---- Ngưỡng nghiệp vụ ----
COLLECTION_RATE_OK = 0.5      # buổi 3: 10 dự án đòi được 5 là tốt
CHASE_MAX_ROUNDS = 7          # buổi 15: đòi tới lần 5–7 nó mới suy nghĩ
OVERDUE_GRACE_DAYS = 7        # quá hạn bao lâu thì bắt đầu nhắc đòi


# ══════════ PHẦN A — SEARCH VOLUME DẠNG KHOẢNG ══════════

@dataclass(frozen=True)
class SearchVolume:
    low: int | None
    high: int | None
    is_range: bool
    raw: str
    display: str
    is_estimate: bool          # True nếu Google chỉ trả khoảng


_UNIT = {"k": 1_000, "m": 1_000_000, "n": 1_000, "tr": 1_000_000}


def _to_int(token: str) -> int | None:
    t = token.strip().lower().replace(",", "").replace(".", "")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([km]|tr|n)?$", token.strip().lower().replace(",", ""))
    if m:
        num = float(m.group(1))
        unit = m.group(2)
        if unit:
            num *= _UNIT.get(unit, 1)
        return int(num)
    return int(t) if t.isdigit() else None


def parse_search_volume(value) -> SearchVolume:
    """Nhận số chính xác (40500) hoặc khoảng ("1K - 10K", "1000–10000") → chuẩn hoá.

    Keyword Planner CHỈ trả số chính xác khi tài khoản có camp đang chi tiêu đủ;
    còn lại trả khoảng → phải chấm điểm theo CẬN DƯỚI cho an toàn.
    """
    if value is None:
        return SearchVolume(None, None, False, "", "chưa có dữ liệu", False)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = int(value)
        return SearchVolume(n, n, False, str(value), f"{n:,}".replace(",", "."), False)

    raw = str(value).strip()
    parts = re.split(r"\s*(?:-|–|—|to|đến)\s*", raw, maxsplit=1)
    if len(parts) == 2:
        low, high = _to_int(parts[0]), _to_int(parts[1])
        if low is not None and high is not None:
            disp = f"{low:,}–{high:,}".replace(",", ".")
            return SearchVolume(low, high, True, raw, disp, True)

    n = _to_int(raw)
    if n is not None:
        return SearchVolume(n, n, False, raw, f"{n:,}".replace(",", "."), False)
    return SearchVolume(None, None, False, raw, "không đọc được", False)


def search_volume_verdict(sv: SearchVolume, threshold: int = 2000) -> tuple[bool | None, str]:
    """Chấm theo CẬN DƯỚI — thà bỏ sót còn hơn chạy nhầm dự án yếu.

    Trả (đạt?, giải thích). đạt=None nghĩa là chưa kết luận được.
    """
    if sv.low is None:
        return None, "Chưa có dữ liệu lượt tìm kiếm."
    if not sv.is_range:
        ok = sv.low >= threshold
        explanation = (
            f"{sv.display}/tháng — {'đạt' if ok else 'chưa đạt'} ngưỡng {threshold:,}"
        )
        return ok, explanation.replace(",", ".")

    if sv.low >= threshold:
        explanation = f"Khoảng {sv.display}: cận dưới đã ≥ {threshold:,} → ĐẠT chắc chắn."
        return True, explanation.replace(",", ".")
    if sv.high is not None and sv.high < threshold:
        explanation = f"Khoảng {sv.display}: cận trên vẫn < {threshold:,} → KHÔNG đạt."
        return False, explanation.replace(",", ".")
    return None, (
        f"Khoảng {sv.display} — CHƯA KẾT LUẬN ĐƯỢC (có thể {sv.low:,} hoặc {sv.high:,}). "
        "Google chỉ trả số chính xác khi tài khoản có chiến dịch đang chi tiêu. "
        "Tạm chấm theo cận dưới; nên kiểm tra tay trước khi quyết."
    ).replace(",", ".")


# ══════════ PHẦN B — LỜI LÃI THẬT ══════════

@dataclass(frozen=True)
class CommissionRow:
    project_id: int
    amount_usd: Decimal
    state: str                 # PENDING | APPROVED | LOCKED | PAID
    converted_on: date
    clear_days: int | None = None      # chu kỳ duyệt của dự án
    pay_days: int | None = None        # chu kỳ trả sau khi duyệt (NET-30…)
    paid_on: date | None = None


@dataclass(frozen=True)
class SpendRow:
    project_id: int
    amount_usd: Decimal
    account_rent_usd: Decimal = D0     # thuê invoice ($5–10/acc)
    spend_fee_pct: Decimal = D0        # phí % trên spend (5–7%)


@dataclass(frozen=True)
class ProjectPnL:
    project_id: int
    spend: Decimal              # chi ads
    variable_cost: Decimal      # thuê acc + % spend
    total_cost: Decimal
    on_web: Decimal             # tiền còn treo trên dashboard (CHƯA phải của mình)
    withdrawn: Decimal          # tiền THỰC rút về
    real_profit: Decimal        # withdrawn − total_cost
    expected_dates: list[tuple[date, Decimal]] = field(default_factory=list)
    overdue: list[tuple[date, Decimal]] = field(default_factory=list)

    @property
    def is_profitable(self) -> bool:
        return self.real_profit > 0


def expected_pay_date(row: CommissionRow) -> date | None:
    """Ngày tiền DỰ KIẾN về = ngày chuyển đổi + clear time + pay time."""
    if row.clear_days is None and row.pay_days is None:
        return None
    return row.converted_on + timedelta(days=(row.clear_days or 0) + (row.pay_days or 0))


def project_pnl(
    project_id: int,
    commissions: list[CommissionRow],
    spends: list[SpendRow],
    today: date,
) -> ProjectPnL:
    spend = sum((s.amount_usd for s in spends), D0)
    variable = sum(
        (s.account_rent_usd + s.amount_usd * s.spend_fee_pct / Decimal("100") for s in spends),
        D0,
    )
    on_web = sum((c.amount_usd for c in commissions if c.state != "PAID"), D0)
    withdrawn = sum((c.amount_usd for c in commissions if c.state == "PAID"), D0)

    expected: list[tuple[date, Decimal]] = []
    overdue: list[tuple[date, Decimal]] = []
    for c in commissions:
        if c.state == "PAID":
            continue
        eta = expected_pay_date(c)
        if eta is None:
            continue
        expected.append((eta, c.amount_usd))
        if today > eta + timedelta(days=OVERDUE_GRACE_DAYS):
            overdue.append((eta, c.amount_usd))

    total_cost = spend + variable
    return ProjectPnL(
        project_id=project_id,
        spend=spend,
        variable_cost=variable,
        total_cost=total_cost,
        on_web=on_web,
        withdrawn=withdrawn,
        real_profit=withdrawn - total_cost,
        expected_dates=sorted(expected),
        overdue=sorted(overdue),
    )


@dataclass
class PortfolioSummary:
    total_spend: Decimal
    total_variable: Decimal
    total_on_web: Decimal
    total_withdrawn: Decimal
    real_profit: Decimal
    collection_rate: float | None      # tiền rút được / tiền đã kiếm
    projects_paid: int
    projects_with_earnings: int
    alerts: list[str] = field(default_factory=list)


def portfolio_summary(pnls: list[ProjectPnL]) -> PortfolioSummary:
    spend = sum((p.spend for p in pnls), D0)
    variable = sum((p.variable_cost for p in pnls), D0)
    on_web = sum((p.on_web for p in pnls), D0)
    withdrawn = sum((p.withdrawn for p in pnls), D0)
    with_earn = [p for p in pnls if (p.on_web + p.withdrawn) > 0]
    paid = [p for p in pnls if p.withdrawn > 0]
    rate = (len(paid) / len(with_earn)) if with_earn else None

    alerts: list[str] = []
    if on_web > 0:
        alerts.append(
            f"${on_web:,.0f} đang treo trên dashboard — CHƯA phải lợi nhuận. "
            "Chỉ tính khi tiền về túi.".replace(",", ".")
        )
    if rate is not None and rate < COLLECTION_RATE_OK:
        alerts.append(
            f"Tỷ lệ đòi được tiền {rate:.0%} ({len(paid)}/{len(with_earn)} dự án) — "
            f"dưới mức bình thường (~{COLLECTION_RATE_OK:.0%}). Rà lại khâu đòi tiền."
        )
    overdue_total = sum((amt for p in pnls for _, amt in p.overdue), D0)
    if overdue_total > 0:
        alerts.append(
            f"${overdue_total:,.0f} đã QUÁ HẠN trả — bắt đầu quy trình đòi tiền "
            f"(đòi tới lần {CHASE_MAX_ROUNDS} mới bỏ).".replace(",", ".")
        )
    if withdrawn - (spend + variable) < 0 and withdrawn > 0:
        alerts.append("Đang LỖ trên tiền thực rút — soát lại dự án hoặc chi phí quảng cáo.")

    return PortfolioSummary(
        total_spend=spend,
        total_variable=variable,
        total_on_web=on_web,
        total_withdrawn=withdrawn,
        real_profit=withdrawn - spend - variable,
        collection_rate=rate,
        projects_paid=len(paid),
        projects_with_earnings=len(with_earn),
        alerts=alerts,
    )
