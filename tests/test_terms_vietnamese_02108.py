from __future__ import annotations

import json

from afi_os.services.camp_generator import generate_camp_plan
from afi_os.services.llm_extractor import PPC_UNDISCLOSED_VI, parse_and_validate

SOURCE = (
    "Partners earn 30% recurring commissions for the lifetime of each customer. "
    "Payouts are sent via PayPal after 30 days with a minimum payout of $50. "
    "Paid search ads are not allowed in the affiliate program."
)


def _translated_response(*, terms_quote: str) -> str:
    return json.dumps(
        {
            "commission": {
                "type": "RECURRING_LIFETIME",
                "percent": 30,
                "rate_is_upper_bound": False,
                "recurring_months": None,
                "flat_usd": None,
                "quote": (
                    "Partners earn 30% recurring commissions for the lifetime of "
                    "each customer."
                ),
                "quote_vi": "Đối tác nhận 30% hoa hồng định kỳ trong suốt vòng đời khách hàng.",
                "summary_vi": "Hoa hồng 30% định kỳ trọn đời.",
            },
            "packages": [],
            "payment": {"gateways": None, "quote": None},
            "terms": {
                "ads_allowed": False,
                "brand_bid_restricted": None,
                "direct_link_allowed": None,
                "trademark_plus_coupon_banned": None,
                "quote": terms_quote,
                "quote_vi": "Không được chạy quảng cáo tìm kiếm trả phí.",
                "summary_vi": "Dự án cấm quảng cáo tìm kiếm trả phí.",
            },
            "ppc_policy_vi": (
                "Không được chạy Google Ads; trang chưa nói rõ brand bid hay direct link."
            ),
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )


def test_vietnamese_fields_are_kept_but_original_quote_is_the_guard() -> None:
    result = parse_and_validate(
        _translated_response(
            terms_quote="Paid search ads are not allowed in the affiliate program."
        ),
        [("https://example.test/terms", SOURCE)],
    )

    terms = next(item for item in result.facts if item.scope == "TERMS")
    ppc = next(item for item in result.facts if item.scope == "PPC_POLICY_VI")
    assert terms.quote_vi == "Không được chạy quảng cáo tìm kiếm trả phí."
    assert terms.summary_vi == "Dự án cấm quảng cáo tìm kiếm trả phí."
    assert "quote_vi" not in terms.payload
    assert ppc.summary_vi.startswith("Không được chạy Google Ads")


def test_a_fake_original_quote_is_rejected_even_with_a_plausible_translation() -> None:
    result = parse_and_validate(
        _translated_response(terms_quote="Paid search is fully allowed for all partners."),
        [("https://example.test/terms", SOURCE)],
    )

    assert all(item.scope != "TERMS" for item in result.facts)
    assert any("chống bịa" in reason for reason in result.rejected)


def test_missing_ppc_source_uses_the_required_warning_instead_of_inventing_permission() -> None:
    response = json.loads(_translated_response(terms_quote=""))
    response["terms"] = {"ads_allowed": None, "quote": None}
    response["ppc_policy_vi"] = "PPC chắc chắn được phép."
    result = parse_and_validate(
        json.dumps(response, ensure_ascii=False),
        [("https://example.test/terms", SOURCE.split("Paid search")[0])],
    )

    ppc = next(item for item in result.facts if item.scope == "PPC_POLICY_VI")
    assert ppc.summary_vi == PPC_UNDISCLOSED_VI
    assert all(item.scope != "TERMS" for item in result.facts)


def test_step_two_ad_assets_remain_english_ascii() -> None:
    plan = generate_camp_plan(
        "fliki.ai",
        "https://fliki.ai/?via=afi-os-test",
        brand_name="Fliki",
    )
    ad_text = [
        *plan.headlines,
        *plan.descriptions,
        *(item["label"] for item in plan.sitelinks),
        *plan.callouts,
    ]
    assert len(plan.headlines) == 15
    assert len(plan.descriptions) == 4
    assert len(plan.sitelinks) == 4
    assert len(plan.callouts) == 4
    assert all(item.isascii() for item in ad_text)
    assert all("tiếng Việt" not in item for item in ad_text)


def test_page_one_contract_keeps_vietnamese_first_and_original_collapsed() -> None:
    script = (
        __import__("pathlib").Path(__file__).parents[1] / "apps" / "web" / "app.js"
    ).read_text(encoding="utf-8")

    assert "TÓM TẮT ĐIỀU KHOẢN PPC (TIẾNG VIỆT)" in script
    assert "Xem bản gốc" in script
    assert 'item.scope === "PPC_POLICY_VI"' in script
    assert "translatedFactBody(item)" in script
