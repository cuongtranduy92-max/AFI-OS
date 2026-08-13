from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from afi_os.api import portfolio
from afi_os.db import Base, engine
from afi_os.enums import CommissionType, EvidenceReviewStatus, ResearchStatus
from afi_os.main import app
from afi_os.schemas import (
    AppraisalCommission,
    AppraisalFlag,
    AppraisalKeyword,
    AppraisalPayback,
    AppraisalTerms,
    AppraisalTraffic,
)
from afi_os.services.appraisal import (
    _commission_display,
    _offer_packages,
    score_appraisal,
)

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_appraise_returns_exact_contract_and_explicit_pending_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        portfolio,
        "collect_domain_proposal",
        lambda db, domain: {
            "run": SimpleNamespace(status=ResearchStatus.MANUAL_INPUT_REQUIRED),
            "program": None,
            "source_urls": [],
        },
    )
    monkeypatch.setattr(
        portfolio,
        "collect_project_traffic",
        lambda db, project: {
            "status": "CONNECTION_REQUIRED",
            "provider": None,
            "detail": "Traffic provider chưa kết nối.",
            "requires_user": True,
            "fields": ["website_traffic_monthly", "top_traffic_countries"],
            "source_urls": [],
            "setup_command": "SETUP-TRAFFIC-DATA.command",
        },
    )
    monkeypatch.setattr(
        portfolio,
        "collect_project_keyword_metrics",
        lambda db, project: {
            "status": "CONNECTION_REQUIRED",
            "detail": "Google Ads API chưa sẵn sàng.",
            "requires_user": True,
            "fields": [
                "primary_keyword_search_volume",
                "primary_keyword_bid_low",
                "primary_keyword_bid_high",
            ],
            "source_urls": [],
        },
    )

    response = client.post("/api/appraise", json={"domain": "dot-one.example"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "domain",
        "niche",
        "affiliate_link",
        "traffic",
        "keyword",
        "advertisers",
        "commission",
        "payment",
        "terms",
        "payback",
        "score",
    }
    assert set(body["traffic"]) == {
        "monthly",
        "top_countries",
        "source",
        "source_status",
    }
    assert body["traffic"]["monthly"] is None
    assert body["traffic"]["source_status"] == "pending"
    assert body["keyword"]["search_volume"] is None
    assert body["advertisers"]["count"] is None
    assert body["commission"]["percent"] is None
    assert body["payback"]["days_high"] is None
    assert body["score"]["total"] == 0
    assert body["score"]["pass"] is None
    assert any(item["level"] == "pending" for item in body["score"]["flags"])


def test_score_appraisal_applies_exact_thresholds_and_warning_only_terms() -> None:
    score = score_appraisal(
        AppraisalTraffic(monthly=25_000),
        AppraisalKeyword(search_volume=3_000),
        AppraisalPayback(days_low=170.4, days_high=119.9),
        AppraisalCommission(type="recurring", percent=30),
        AppraisalTerms(ads_allowed=False, brand_bid_restricted=True),
        [AppraisalFlag(level="warning", msg="Nguồn terms cần theo dõi.")],
    )

    assert score.total == 100
    assert score.pass_ is True
    assert any("CẤM chạy Google Ads" in item.msg for item in score.flags)
    assert any("Cấm bid" in item.msg for item in score.flags)


def test_score_appraisal_fails_core_but_never_excludes_for_terms_or_one_time() -> None:
    score = score_appraisal(
        AppraisalTraffic(monthly=20_000),
        AppraisalKeyword(search_volume=2_000),
        AppraisalPayback(days_low=120.1, days_high=140),
        AppraisalCommission(type="one_time", percent=40),
        AppraisalTerms(ads_allowed=False),
        [],
    )

    assert score.total == 0
    assert score.pass_ is False
    messages = [item.msg for item in score.flags]
    assert any(message.startswith("Traffic") for message in messages)
    assert any(message.startswith("Search") for message in messages)
    assert "Hoàn vốn > 120 ngày." in messages
    assert any("chỉ cảnh báo" in message for message in messages)
    assert any("one-time" in message for message in messages)


def test_appraise_rejects_non_domain_input() -> None:
    response = client.post("/api/appraise", json={"domain": "not a domain"})

    assert response.status_code == 422


def test_accepted_maximum_commission_is_displayed_but_kept_out_of_payback() -> None:
    project = SimpleNamespace(
        program=SimpleNamespace(
            commission_facts=[
                SimpleNamespace(
                    id=1,
                    checked_at=datetime.now(UTC),
                    review_status=EvidenceReviewStatus.ACCEPTED,
                    confidence=0.84,
                    commission_type=CommissionType.RECURRING_LIFETIME,
                    commission_rate=Decimal("0.50"),
                    rate_is_maximum=True,
                )
            ],
            offers=[
                SimpleNamespace(active=True, name="Standard", price=Decimal("28")),
                SimpleNamespace(active=True, name="Premium", price=Decimal("88")),
            ],
        )
    )

    commission_type, percent, is_maximum = _commission_display(project, None, None)

    assert commission_type == "recurring"
    assert percent == 50
    assert is_maximum is True
    assert _offer_packages(project) == [("Standard", 28), ("Premium", 88)]
