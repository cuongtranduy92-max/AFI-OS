from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from afi_os.services.llm_extractor import parse_and_validate
from afi_os.services.true_profit import (
    CommissionRow,
    SpendRow,
    parse_search_volume,
    portfolio_summary,
    project_pnl,
    search_volume_verdict,
)


def test_search_volume_preserves_exact_and_range_values() -> None:
    exact = parse_search_volume(40500)
    ambiguous = parse_search_volume("1K - 10K")
    passing = parse_search_volume("10K–100K")
    failing = parse_search_volume("500-1500")

    assert (exact.display, search_volume_verdict(exact)[0], exact.is_estimate) == (
        "40.500",
        True,
        False,
    )
    assert (ambiguous.display, search_volume_verdict(ambiguous)[0]) == (
        "1.000–10.000",
        None,
    )
    assert (passing.display, search_volume_verdict(passing)[0]) == (
        "10.000–100.000",
        True,
    )
    assert (failing.display, search_volume_verdict(failing)[0]) == (
        "500–1.500",
        False,
    )


def test_true_profit_uses_only_paid_cash_and_includes_invoice_fees() -> None:
    today = date(2026, 8, 13)
    fliki = project_pnl(
        1,
        [
            CommissionRow(
                project_id=1,
                amount_usd=Decimal("1704"),
                state="PAID",
                converted_on=date(2026, 6, 1),
                paid_on=date(2026, 7, 1),
            )
        ],
        [
            SpendRow(
                project_id=1,
                amount_usd=Decimal("253"),
                account_rent_usd=Decimal("10"),
                spend_fee_pct=Decimal("5"),
            )
        ],
        today,
    )
    heartbeat = project_pnl(
        2,
        [
            CommissionRow(
                project_id=2,
                amount_usd=Decimal("540"),
                state="APPROVED",
                converted_on=date(2026, 5, 1),
                clear_days=30,
                pay_days=30,
            )
        ],
        [
            SpendRow(
                project_id=2,
                amount_usd=Decimal("141"),
                account_rent_usd=Decimal("10"),
                spend_fee_pct=Decimal("5"),
            )
        ],
        today,
    )
    snov = project_pnl(
        3,
        [],
        [
            SpendRow(
                project_id=3,
                amount_usd=Decimal("167"),
                account_rent_usd=Decimal("10"),
                spend_fee_pct=Decimal("5"),
            )
        ],
        today,
    )

    summary = portfolio_summary([fliki, heartbeat, snov])

    assert summary.total_spend == Decimal("561")
    assert summary.total_variable == Decimal("58.05")
    assert summary.total_on_web == Decimal("540")
    assert summary.total_withdrawn == Decimal("1704")
    assert summary.real_profit == Decimal("1084.95")
    assert summary.collection_rate == 0.5
    assert heartbeat.overdue == [(date(2026, 6, 30), Decimal("540"))]
    assert any("CHƯA phải lợi nhuận" in alert for alert in summary.alerts)
    assert any("QUÁ HẠN" in alert for alert in summary.alerts)


def test_page_four_and_manual_pricing_controls_are_visible() -> None:
    page = Path("apps/web/index.html").read_text(encoding="utf-8")
    script = Path("apps/web/app.js").read_text(encoding="utf-8")

    assert "Tiền trên web (chưa về)" in script
    assert "Tiền THỰC rút" in script
    assert "LỜI LÃI THẬT" in script
    assert 'request("/finance/true-profit")' in script
    assert "data-manual-package" in script
    assert 'id="trueProfitRows"' in page
    assert 'id="commissionImportForm"' in page


def test_ppc_checklist_downgrades_a_claim_when_quote_is_not_in_source() -> None:
    source_quote = "Paid search advertising is allowed, except trademark bidding is prohibited."
    payload = {
        "ppc_policy": {
            "search_ads_allowed": {
                "status": "ALLOWED",
                "quote": source_quote,
                "quote_vi": "Được chạy quảng cáo tìm kiếm.",
                "note_vi": "Có thể chạy Search Ads nhưng phải xem các hạn chế khác.",
            },
            "brand_keyword_bidding": {
                "status": "ALLOWED",
                "quote": "Affiliates may bid on every trademark without restriction.",
                "quote_vi": "Được đặt thầu mọi thương hiệu.",
                "note_vi": "Câu này không có trong nguồn.",
            },
            "overall_verdict_vi": "Có thể chạy Search Ads nhưng không tự suy ra quyền brand bid.",
        },
        "confidence": 0.9,
    }

    result = parse_and_validate(
        json.dumps(payload),
        [("https://merchant.example/terms", source_quote, "terms")],
    )
    checklist = next(item for item in result.facts if item.scope == "PPC_CHECKLIST")

    assert checklist.payload["items"]["search_ads_allowed"]["status"] == "ALLOWED"
    assert checklist.payload["items"]["brand_keyword_bidding"]["status"] == "NOT_STATED"
    assert any("brand_keyword_bidding" in reason for reason in result.rejected)
    assert all(
        checklist.payload["items"][key]["status"] == "NOT_STATED"
        for key in (
            "direct_linking",
            "brand_in_ad_copy",
            "brand_in_display_url",
            "trademark_plus_coupon",
        )
    )
