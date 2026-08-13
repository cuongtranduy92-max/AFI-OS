from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    EvidenceReviewStatus,
    PermissionStatus,
    ResearchStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import (
    AdsAccount,
    Campaign,
    CampaignProgramLink,
    Merchant,
    Program,
    TermsEvidence,
    TermsResearchRun,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_campaign_program() -> tuple[int, int]:
    with SessionLocal() as db:
        merchant = Merchant(name="Grouped", website_domain="grouped.example")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Grouped Affiliate Program")
        account = AdsAccount(
            external_id="500-500-5000",
            name="Grouped Google Ads",
            currency="USD",
        )
        db.add_all([program, account])
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            external_id="grouped-campaign-1",
            name="Grouped Search Campaign",
            status="ENABLED",
            channel_type="SEARCH",
            currency="USD",
        )
        db.add(campaign)
        db.flush()
        db.add(CampaignProgramLink(campaign_id=campaign.id, program_id=program.id))
        db.commit()
        return program.id, campaign.id


def _research(program_id: int, status: ResearchStatus) -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                program_id=program_id,
                domain="grouped.example",
                fixture_version="grouping-test-v1",
                status=status,
                checked_at=now,
                discovery_confidence=0.9,
                source_urls=["https://grouped.example/affiliate"],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash=f"grouping-{status.value}-{now.timestamp()}",
                summary="No public PPC permission found.",
            )
        )
        db.commit()


def test_successful_no_permission_scan_absorbs_same_program_campaign_warning() -> None:
    program_id, _ = _seed_campaign_program()
    _research(program_id, ResearchStatus.PROPOSAL_READY)

    inbox = client.get("/api/operations/inbox").json()
    assert inbox["open_count"] == 1
    assert inbox["requires_user_count"] == 0
    assert inbox["warning_count"] == 1
    assert inbox["counts_by_type"] == {"TERMS_PERMISSION_NOT_FOUND": 1}
    item = inbox["items"][0]
    assert item["key"] == f"TERMS_NO_PERMISSION_EVIDENCE:{program_id}"
    assert "1 campaign đang chạy" in item["title"]
    assert "Grouped Search Campaign" in item["detail"]
    assert "không bị loại hoặc dừng" in item["detail"]
    assert item["action_view"] == "programs"

    stored = client.get("/api/programs").json()[0]
    assert stored["paid_search_permission"] == "NOT_CHECKED"
    assert stored["brand_keyword_permission"] == "NOT_CHECKED"
    assert stored["non_brand_permission"] == "NOT_CHECKED"


def test_manual_source_exception_absorbs_same_program_campaign_warning() -> None:
    program_id, _ = _seed_campaign_program()
    _research(program_id, ResearchStatus.MANUAL_INPUT_REQUIRED)

    inbox = client.get("/api/operations/inbox").json()
    assert inbox["open_count"] == 1
    assert inbox["requires_user_count"] == 1
    assert inbox["warning_count"] == 0
    assert inbox["counts_by_type"] == {"TERMS_SOURCE_REQUIRED": 1}
    item = inbox["items"][0]
    assert item["key"] == "TERMS_MANUAL:grouped.example"
    assert "1 campaign đang chạy" in item["title"]
    assert "Grouped Search Campaign" in item["detail"]
    assert item["requires_user"] is True


def test_not_checked_evidence_absorbs_same_program_campaign_warning() -> None:
    program_id, _ = _seed_campaign_program()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            TermsEvidence(
                program_id=program_id,
                source_url="https://grouped.example/affiliate-terms",
                excerpt="The public page does not state a paid-search rule.",
                evidence_hash="grouped-not-checked-evidence",
                checked_at=now,
                reviewer="grouping-test",
                confidence=0.0,
                decision=PermissionStatus.NOT_CHECKED,
                scope="PAID_SEARCH",
                applies_to="PAID_SEARCH",
                review_status=EvidenceReviewStatus.PROPOSED,
                source_authority=SourceAuthority.OFFICIAL,
            )
        )
        db.commit()

    inbox = client.get("/api/operations/inbox").json()
    assert inbox["open_count"] == 1
    assert inbox["requires_user_count"] == 0
    assert inbox["warning_count"] == 1
    assert inbox["counts_by_type"] == {"TERMS_PERMISSION_UNVERIFIED": 1}
    item = inbox["items"][0]
    assert item["key"] == f"TERMS_UNVERIFIED:{program_id}"
    assert "1 campaign đang chạy" in item["title"]
    assert "Grouped Search Campaign" in item["detail"]
