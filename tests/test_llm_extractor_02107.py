from __future__ import annotations

import json

from afi_os.services.llm_extractor import (
    MAX_PAGE_CHARS,
    build_extraction_prompt,
    parse_and_validate,
)

SOURCE = (
    "Partners earn 30% recurring commissions for the lifetime of each customer. "
    "Payouts are sent via PayPal after 30 days with a minimum payout of $50. "
    "Paid search ads are not allowed in the affiliate program."
)


def _payload(*, commission_quote: str, upper_bound: bool = False) -> str:
    return json.dumps(
        {
            "commission": {
                "type": "RECURRING_LIFETIME",
                "percent": 50 if upper_bound else 30,
                "rate_is_upper_bound": upper_bound,
                "recurring_months": None,
                "flat_usd": None,
                "quote": commission_quote,
            },
            "packages": [],
            "payment": {"gateways": None, "quote": None},
            "terms": {"ads_allowed": None, "quote": None},
            "confidence": 0.95,
        }
    )


def test_quote_guard_rejects_a_modified_quote() -> None:
    pages = [("https://example.test/terms", SOURCE)]
    result = parse_and_validate(
        _payload(commission_quote="Partners earn 99% guaranteed commissions forever."),
        pages,
    )

    assert all(fact.scope != "COMMISSION" for fact in result.facts)
    assert any("chống bịa" in reason for reason in result.rejected)


def test_up_to_rate_remains_a_proposal_warning() -> None:
    source = "Partners may earn up to 50% recurring commissions for the lifetime of a customer."
    result = parse_and_validate(
        _payload(commission_quote=source, upper_bound=True),
        [("https://example.test/terms", source)],
    )

    commission = next(fact for fact in result.facts if fact.scope == "COMMISSION")
    assert commission.payload["rate_is_upper_bound"] is True
    assert commission.confidence == 0.855
    assert any("KHÔNG dùng payback" in reason for reason in result.rejected)


def test_prompt_caps_each_page_at_fifteen_thousand_characters() -> None:
    marker = "z" * (MAX_PAGE_CHARS + 1000)
    _, prompt = build_extraction_prompt("example.test", [("https://example.test", marker)])

    assert "z" * MAX_PAGE_CHARS in prompt
    assert "z" * (MAX_PAGE_CHARS + 1) not in prompt
