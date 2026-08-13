from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import CommissionType, EvidenceReviewStatus, PermissionStatus
from afi_os.main import app
from afi_os.models import (
    AdObservation,
    Advertiser,
    AuditLog,
    Campaign,
    CommissionFact,
    Program,
    TermsEvidence,
)
from afi_os.services import terms_research
from afi_os.services.truth_repairs import repair_automated_truth_semantics

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _snov_terms(_domain: str, **_kwargs):
    return (
        [
            {
                "url": "https://snov.io/affiliate-terms",
                "title": "Snov.io Affiliate Program Terms",
                "text": (
                    "The affiliate will receive a 40% commission for every plan purchase "
                    "made by each referred user, applicable for the entire duration of "
                    "their subscription. Additionally, for each LinkedIn Automation slot "
                    "sold through the affiliate's referral link, the affiliate will earn "
                    "a 20% commission on the slot's purchase price. "
                    "The Affiliate is not allowed to use PPC bidding brand names "
                    "(Snov.io, Snov, Snovio) in any PPC advertisements without prior "
                    "written permission. To avoid accidental brand bidding, affiliates "
                    "are required to include Snov.io branded terms as negative keywords "
                    "in all PPC campaigns where applicable."
                ),
                "links": [],
            }
        ],
        [],
    )


def test_snov_terms_are_scoped_and_product_rates_are_not_a_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terms_research, "discover_official_pages", _snov_terms)

    response = client.post("/api/programs/research", json={"domain": "snov.io"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert {
        (item["scope"], item["decision"])
        for item in body["terms_evidence"]
    } == {
        ("PAID_SEARCH", "NON_BRAND_ONLY"),
        ("NON_BRAND", "NON_BRAND_ONLY"),
        ("BRAND_KEYWORD", "APPROVAL_REQUIRED"),
    }
    assert body["commission_state"] == "PROPOSED"
    assert {
        (
            item["commission_rate"],
            item["commission_type"],
            item["applies_to"],
        )
        for item in body["commission_facts"]
    } == {
        ("0.400000", "RECURRING_LIFETIME", "PLAN_SUBSCRIPTION"),
        ("0.200000", "ONE_TIME", "LINKEDIN_AUTOMATION_SLOT"),
    }
    program = client.get("/api/programs").json()[0]
    assert program["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert program["commission_state"] == "PROPOSED"
    for field in (
        "paid_search_permission",
        "brand_keyword_permission",
        "non_brand_permission",
        "direct_link_permission",
        "trademark_in_ad_copy_permission",
    ):
        assert program[field] == PermissionStatus.NOT_CHECKED.value

    with SessionLocal() as db:
        legacy_evidence = db.scalar(
            select(TermsEvidence).where(
                TermsEvidence.scope == "PAID_SEARCH",
                TermsEvidence.decision == PermissionStatus.NON_BRAND_ONLY,
            )
        )
        legacy_fact = db.scalar(
            select(CommissionFact).where(CommissionFact.commission_rate == 0.4)
        )
        assert legacy_evidence is not None and legacy_fact is not None
        assert repair_automated_truth_semantics(db)["evidence_repaired"] == 0
        assert legacy_evidence.review_status == EvidenceReviewStatus.PROPOSED

        legacy_evidence.review_status = EvidenceReviewStatus.REJECTED
        legacy_evidence.notes = (
            "truth-semantic-repair-v1: conditional brand-bidding policy was re-scoped; "
            "operator acceptance remains required."
        )
        db.commit()
        restored = repair_automated_truth_semantics(db)
        db.commit()
        assert restored["evidence_repaired"] == 1
        assert legacy_evidence.review_status == EvidenceReviewStatus.PROPOSED

        legacy_evidence.decision = PermissionStatus.PROHIBITED
        legacy_fact.commission_type = CommissionType.RECURRING_UNSPECIFIED
        legacy_fact.applies_to = "RECURRING_UNSPECIFIED"
        db.commit()
        repaired = repair_automated_truth_semantics(db)
        db.commit()
        assert repaired["evidence_repaired"] == 1
        assert repaired["facts_repaired"] == 1
        assert legacy_evidence.review_status.value == "REJECTED"
        assert legacy_fact.commission_type.value == "RECURRING_LIFETIME"
        assert legacy_fact.applies_to == "PLAN_SUBSCRIPTION"
        assert repair_automated_truth_semantics(db)["evidence_repaired"] == 0
        assert repair_automated_truth_semantics(db)["facts_repaired"] == 0


def test_sourced_advertiser_batch_is_idempotent_and_never_fakes_activity() -> None:
    project = next(
        item for item in client.get("/api/portfolio/projects").json() if item["domain"] == "snov.io"
    )
    with SessionLocal() as db:
        program = db.get(Program, project["program_id"])
        assert program is not None
        permissions_before = (
            program.paid_search_permission,
            program.brand_keyword_permission,
            program.non_brand_permission,
            program.direct_link_permission,
            program.trademark_in_ad_copy_permission,
        )
        campaign_count_before = db.scalar(select(func.count()).select_from(Campaign))

    payload = {
        "project_domain": "snov.io",
        "source_url": "https://source.example/results?snov.io",
        "source_name": "Bounded advertiser result",
        "checked_at": "2026-08-12T13:09:54Z",
        "evidence_excerpt": "Danh sách nhà quảng cáo cho snov.io: Snov.io 72 QC; Example 3 QC.",
        "geography": "ANYWHERE",
        "result_set_complete": True,
        "confidence": 0.85,
        "actor": "Snov truth test",
        "advertisers": [
            {
                "external_key": "AR-SNOV",
                "advertiser_name": "Snov.io",
                "reported_ad_count": 72,
            },
            {
                "external_key": "AR-EXAMPLE",
                "advertiser_name": "Example Advertiser",
                "reported_ad_count": 3,
            },
        ],
    }
    first = client.post("/api/ad-intelligence/advertiser-snapshots", json=payload)
    duplicate = client.post("/api/ad-intelligence/advertiser-snapshots", json=payload)

    assert first.status_code == 200, first.text
    assert first.json()["advertisers_created"] == 2
    assert first.json()["observations_created"] == 2
    assert first.json()["reported_ads"] == 75
    assert first.json()["google_ads_write"] is False
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["duplicate"] is True

    item = client.get(f"/api/portfolio/projects/{project['id']}").json()
    independent = item["metrics"]["independent_advertisers"]
    active = item["metrics"]["active_advertisers_30d"]
    assert independent["value"] == 2
    assert independent["quality"] == "IMPORTED"
    assert independent["collection_state"] == "AVAILABLE"
    assert independent["source_url"].startswith("https://source.example/")
    assert active["value"] is None
    assert active["collection_state"] == "PARTIAL"
    assert "ADVERTISER_DATA_MISSING" not in item["risk_badges"]

    radar = next(
        item
        for item in client.get("/api/ad-intelligence/radar").json()
        if item["domain"] == "snov.io"
    )
    assert radar["distinct_advertisers"] == 2
    assert radar["active_advertisers_30d"] is None
    assert radar["independent_advertiser_score"] is None
    assert radar["top_advertiser_share"] == 0.96

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Advertiser)) == 2
        assert db.scalar(select(func.count()).select_from(AdObservation)) == 2
        program = db.get(Program, project["program_id"])
        assert program is not None
        assert (
            program.paid_search_permission,
            program.brand_keyword_permission,
            program.non_brand_permission,
            program.direct_link_permission,
            program.trademark_in_ad_copy_permission,
        ) == permissions_before
        assert db.scalar(select(func.count()).select_from(Campaign)) == campaign_count_before
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.entity_type == "advertiser_snapshot")
            .order_by(AuditLog.id.desc())
        )
        assert audit is not None
        assert audit.payload_json["permissions_changed"] is False
        assert audit.payload_json["google_ads_write"] is False


def test_invalid_or_duplicate_batch_candidates_create_nothing() -> None:
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AdObservation))
    response = client.post(
        "/api/ad-intelligence/advertiser-snapshots",
        json={
            "project_domain": "snov.io",
            "source_url": "https://source.example/duplicate",
            "source_name": "Duplicate result",
            "checked_at": datetime.now(UTC).isoformat(),
            "evidence_excerpt": "Two duplicate rows.",
            "advertisers": [
                {"external_key": "AR-DUP", "advertiser_name": "One"},
                {"external_key": "AR-DUP", "advertiser_name": "One alias"},
            ],
        },
    )
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AdObservation)) == before


def test_ui_distinguishes_uncollected_from_zero() -> None:
    page = client.get("/").text
    script = client.get("/app.js").text
    assert 'id="advertiserSnapshotForm"' in page
    assert 'independent_advertisers: "Chưa thu thập"' in script
    assert 'active_advertisers_30d: "Chưa đủ dữ liệu"' in script
    assert "collection_state" in script
