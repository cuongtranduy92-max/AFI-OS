from datetime import UTC, datetime, timedelta

from afi_os.services.camp_doctor import (
    CampaignSnapshot,
    ChangeEvent,
    diagnose_campaign,
)

NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)


def _snapshot(**overrides) -> CampaignSnapshot:
    values = {
        "campaign_id": 1,
        "name": "Brand Search",
        "started_at": NOW - timedelta(days=10),
        "impressions": 1000,
        "clicks": 500,
        "cost_usd": 35,
        "refs": 10,
    }
    values.update(overrides)
    return CampaignSnapshot(**values)


def _codes(result) -> set[str]:
    return {item.code for item in result.findings}


def test_new_campaign_under_24_hours_is_learning_without_edit_advice() -> None:
    result = diagnose_campaign(
        _snapshot(started_at=NOW - timedelta(hours=12)),
        changes=[ChangeEvent("budget", 50, 100, NOW - timedelta(hours=1))],
        now=NOW,
    )
    assert result.status == "LEARNING"
    assert _codes(result) == {"LEARNING_24H"}
    assert result.next_actions == ["Để yên, kiểm tra lại sau 24–48h"]


def test_low_ctr_with_competitor_says_raise_bid_not_broken_campaign() -> None:
    result = diagnose_campaign(
        _snapshot(clicks=100, competitors_on_keyword=True), now=NOW
    )
    assert "LOW_BID_WITH_COMPETITOR" in _codes(result)
    joined = " ".join(
        [item.message + " " + item.action for item in result.findings]
    ).lower()
    assert "nâng giá thầu" in joined
    assert "đây không phải camp hỏng" in joined


def test_click_fraud_threshold_and_cpr_bands() -> None:
    fraud = diagnose_campaign(_snapshot(clicks=850), now=NOW)
    assert "CLICK_FRAUD_SUSPECT" in _codes(fraud)
    assert "khiếu nại" in " ".join(item.action for item in fraud.findings).lower()

    good = diagnose_campaign(_snapshot(cost_usd=35, refs=10), now=NOW)
    assert good.cost_per_ref == 3.5
    assert next(item for item in good.findings if item.code == "CPR_GOOD").level == "ok"

    critical = diagnose_campaign(_snapshot(cost_usd=156, refs=10), now=NOW)
    assert critical.cost_per_ref == 15.6
    assert next(
        item for item in critical.findings if item.code == "CPR_CRITICAL"
    ).level == "error"


def test_twenty_percent_too_early_and_waste_search_term_rules() -> None:
    changed = diagnose_campaign(
        _snapshot(),
        changes=[ChangeEvent("budget", 50, 100, NOW - timedelta(hours=2))],
        now=NOW,
    )
    assert next(
        item for item in changed.findings if item.code == "TWENTY_PCT_VIOLATION"
    ).level == "error"

    too_early = diagnose_campaign(
        _snapshot(impressions=100, clicks=30, cost_usd=5, refs=0), now=NOW
    )
    assert "TOO_EARLY" in _codes(too_early)
    assert "NO_REF_AFTER_CLICKS" not in _codes(too_early)

    before_threshold = diagnose_campaign(
        _snapshot(
            clicks=149,
            refs=0,
            search_terms=({"term": "free brand", "clicks": 5, "cost": 3, "refs": 0},),
        ),
        now=NOW,
    )
    assert "WASTE_SEARCH_TERMS" not in _codes(before_threshold)

    at_threshold = diagnose_campaign(
        _snapshot(
            clicks=150,
            refs=0,
            search_terms=({"term": "free brand", "clicks": 5, "cost": 3, "refs": 0},),
        ),
        now=NOW,
    )
    assert "WASTE_SEARCH_TERMS" in _codes(at_threshold)
