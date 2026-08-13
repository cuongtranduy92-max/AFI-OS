from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    AuditAction,
    CommissionType,
    EvidenceReviewStatus,
    FxRateReviewStatus,
    PermissionStatus,
    ReconciliationStatus,
    ResearchStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import (
    AdsAccount,
    AuditLog,
    Campaign,
    CampaignProgramLink,
    CommissionFact,
    FxRate,
    Merchant,
    Program,
    ReconciliationItem,
    TermsEvidence,
    TermsResearchRun,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_operations() -> dict[str, int]:
    with SessionLocal() as db:
        merchant = Merchant(name="Merchant", website_domain="merchant.example.org")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Merchant Affiliate Program")
        db.add(program)
        db.flush()

        evidence = TermsEvidence(
            program_id=program.id,
            source_url="https://merchant.example.org/affiliate-terms",
            excerpt="Paid search is prohibited.",
            evidence_hash="e" * 64,
            checked_at=datetime.now(UTC),
            reviewer="collector",
            confidence=0.9,
            decision=PermissionStatus.PROHIBITED,
            scope="PAID_SEARCH",
            applies_to="PAID_SEARCH",
            review_status=EvidenceReviewStatus.PROPOSED,
            source_authority=SourceAuthority.OFFICIAL,
        )
        fact = CommissionFact(
            program_id=program.id,
            scope="COMMISSION",
            source_url="https://merchant.example.org/affiliate",
            source_authority=SourceAuthority.OFFICIAL,
            excerpt="30% lifetime recurring commission.",
            checked_at=datetime.now(UTC),
            confidence=0.9,
            commission_type=CommissionType.RECURRING_LIFETIME,
            commission_rate=Decimal("0.30"),
            rate_is_maximum=False,
            applies_to="LIFETIME_RECURRING",
            review_status=EvidenceReviewStatus.PROPOSED,
            evidence_hash="c" * 64,
        )
        rate = FxRate(
            rate_date=date.today(),
            from_currency="USD",
            to_currency="VND",
            rate=Decimal("25000"),
            source_name="Official bank",
            source_url="https://bank.example/rates",
            checked_at=datetime.now(UTC),
            confidence=Decimal("0.90"),
            review_status=FxRateReviewStatus.PROPOSED,
            source_hash="f" * 64,
        )
        issue = ReconciliationItem(
            status=ReconciliationStatus.CONFLICT,
            entity_type="COMMISSION",
            entity_id="external-1",
            dedupe_key="r" * 64,
            reason="Cùng ID nhưng số tiền khác nhau.",
            payload_json={},
        )
        manual = TermsResearchRun(
            domain="missing-source.example",
            status=ResearchStatus.MANUAL_INPUT_REQUIRED,
            checked_at=datetime.now(UTC),
            discovery_confidence=0,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="m" * 64,
            summary="No source found.",
        )
        account = AdsAccount(
            external_id="123-456-7890", name="Google Ads", currency="VND"
        )
        db.add_all([evidence, fact, rate, issue, manual, account])
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            external_id="campaign-1",
            name="Merchant search",
            status="ENABLED",
            channel_type="SEARCH",
            currency="VND",
        )
        db.add(campaign)
        db.flush()
        link = CampaignProgramLink(campaign_id=campaign.id, program_id=program.id)
        db.add(link)
        db.commit()
        return {
            "account": account.id,
            "campaign": campaign.id,
            "program": program.id,
            "evidence": evidence.id,
            "fact": fact.id,
            "rate": rate.id,
            "issue": issue.id,
            "manual": manual.id,
            "link": link.id,
        }


def test_operations_inbox_aggregates_decisions_missing_data_and_warnings() -> None:
    ids = _seed_operations()
    response = client.get("/api/operations/inbox")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["open_count"] == 6
    assert body["requires_user_count"] == 5
    assert body["warning_count"] == 1
    assert body["counts_by_type"] == {
        "CAMPAIGN_TERMS_WARNING": 1,
        "COMMISSION_PROGRAM_REVIEW": 1,
        "FX_RATE_REVIEW": 1,
        "RECONCILIATION_REVIEW": 1,
        "TERMS_EVIDENCE_REVIEW": 1,
        "TERMS_SOURCE_REQUIRED": 1,
    }
    keys = {item["key"] for item in body["items"]}
    assert f"TERMS_EVIDENCE:{ids['evidence']}" in keys
    assert f"COMMISSION_REVIEW:{ids['program']}" in keys
    assert f"FX_RATE:{ids['rate']}" in keys
    assert f"RECONCILIATION:{ids['issue']}" in keys
    assert "TERMS_MANUAL:missing-source.example" in keys
    assert all(item["action_view"] in {"programs", "finance", "exposure"} for item in body["items"])
    warning = next(
        item for item in body["items"] if item["item_type"] == "CAMPAIGN_TERMS_WARNING"
    )
    assert warning["requires_user"] is False
    assert "không bị loại hoặc dừng" in warning["detail"]


def test_campaign_terms_warnings_are_grouped_per_program() -> None:
    ids = _seed_operations()
    with SessionLocal() as db:
        second = Campaign(
            ads_account_id=ids["account"],
            external_id="campaign-2",
            name="Merchant search two",
            status="ENABLED",
            channel_type="SEARCH",
            currency="VND",
        )
        db.add(second)
        db.flush()
        db.add(CampaignProgramLink(campaign_id=second.id, program_id=ids["program"]))
        db.commit()

    body = client.get("/api/operations/inbox").json()
    warning_items = [
        item
        for item in body["items"]
        if item["item_type"] == "CAMPAIGN_TERMS_WARNING"
    ]
    assert len(warning_items) == 1
    item = warning_items[0]
    assert item["key"] == f"CAMPAIGN_WARNING_PROGRAM:{ids['program']}"
    assert item["title"].startswith("2 campaign đang chạy")
    assert "Merchant search" in item["detail"]
    assert "Merchant search two" in item["detail"]
    assert item["requires_user"] is False
    assert body["warning_count"] == 1


def test_commission_proposals_are_one_program_level_decision() -> None:
    ids = _seed_operations()
    with SessionLocal() as db:
        db.add(
            CommissionFact(
                program_id=ids["program"],
                scope="COMMISSION",
                source_url="https://merchant.example.org/partner",
                source_authority=SourceAuthority.OFFICIAL,
                excerpt="Up to 50% recurring commission.",
                checked_at=datetime.now(UTC),
                confidence=0.9,
                commission_type=CommissionType.RECURRING_LIFETIME,
                commission_rate=Decimal("0.50"),
                rate_is_maximum=True,
                applies_to="LIFETIME_RECURRING",
                review_status=EvidenceReviewStatus.PROPOSED,
                evidence_hash="d" * 64,
            )
        )
        db.commit()

    body = client.get("/api/operations/inbox").json()
    commission_items = [
        item
        for item in body["items"]
        if item["item_type"] == "COMMISSION_PROGRAM_REVIEW"
    ]
    assert len(commission_items) == 1
    item = commission_items[0]
    assert item["key"] == f"COMMISSION_REVIEW:{ids['program']}"
    assert item["severity"] == "HIGH"
    assert item["requires_user"] is True
    assert item["source_url"] is None
    assert "2 proposal" in item["detail"]
    assert "30% RECURRING_LIFETIME" in item["detail"]
    assert "50% tối đa RECURRING_LIFETIME" in item["detail"]
    assert "một quyết định cấp chương trình" in item["detail"]
    assert body["requires_user_count"] == 5


def test_not_checked_permission_proposals_are_one_tracking_warning() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        merchant = Merchant(name="Unverified", website_domain="unverified.example")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Unverified Affiliate")
        db.add(program)
        db.flush()
        for index, scope in enumerate(
            ("PAID_SEARCH", "BRAND_KEYWORD", "NON_BRAND", "DIRECT_LINK"),
            start=1,
        ):
            db.add(
                TermsEvidence(
                    program_id=program.id,
                    source_url="https://unverified.example/affiliate",
                    excerpt="No explicit affiliate PPC permission was found.",
                    evidence_hash=str(index) * 64,
                    checked_at=now,
                    reviewer="official-web-v1",
                    confidence=0,
                    decision=PermissionStatus.NOT_CHECKED,
                    scope=scope,
                    applies_to=scope,
                    review_status=EvidenceReviewStatus.PROPOSED,
                    source_authority=SourceAuthority.OFFICIAL,
                )
            )
        db.commit()
        program_id = program.id

    body = client.get("/api/operations/inbox").json()
    assert body["open_count"] == 1
    assert body["requires_user_count"] == 0
    assert body["warning_count"] == 1
    assert body["counts_by_type"] == {"TERMS_PERMISSION_UNVERIFIED": 1}
    item = body["items"][0]
    assert item["key"] == f"TERMS_UNVERIFIED:{program_id}"
    assert item["severity"] == "WARNING"
    assert item["requires_user"] is False
    assert item["source_url"] == "https://unverified.example/affiliate"
    assert "4 scope đang NOT_CHECKED" in item["detail"]
    assert "không cần xác nhận proposal" in item["detail"]
    assert "dự án và campaign vẫn được giữ nguyên" in item["detail"]


def test_resolved_items_leave_inbox_and_newer_research_suppresses_manual_request() -> None:
    ids = _seed_operations()
    with SessionLocal() as db:
        db.get(TermsEvidence, ids["evidence"]).review_status = EvidenceReviewStatus.REJECTED
        db.get(CommissionFact, ids["fact"]).review_status = EvidenceReviewStatus.ACCEPTED
        db.get(FxRate, ids["rate"]).review_status = FxRateReviewStatus.REJECTED
        issue = db.get(ReconciliationItem, ids["issue"])
        issue.resolved_at = datetime.now(UTC)
        link = db.get(CampaignProgramLink, ids["link"])
        link.risk_acknowledged_at = datetime.now(UTC)
        db.add(
            TermsResearchRun(
                domain="missing-source.example",
                status=ResearchStatus.PROPOSAL_READY,
                checked_at=datetime.now(UTC) + timedelta(seconds=1),
                discovery_confidence=0.9,
                source_urls=["https://missing-source.example/affiliate"],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash="n" * 64,
                summary="Proposal found.",
            )
        )
        db.commit()

    body = client.get("/api/operations/inbox").json()
    assert body["open_count"] == 0
    assert body["requires_user_count"] == 0
    assert body["warning_count"] == 0
    assert body["items"] == []


def test_operations_selects_latest_research_heartbeat_not_source_date() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        proposal = TermsResearchRun(
            domain="heartbeat-operations.example",
            status=ResearchStatus.PROPOSAL_READY,
            checked_at=now - timedelta(hours=30),
            created_at=now - timedelta(hours=30),
            updated_at=now - timedelta(hours=30),
            discovery_confidence=0.9,
            source_urls=["https://heartbeat-operations.example/affiliate"],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="operations-source-newer".ljust(64, "p"),
            summary="Older successful attempt.",
        )
        manual = TermsResearchRun(
            domain="heartbeat-operations.example",
            status=ResearchStatus.MANUAL_INPUT_REQUIRED,
            checked_at=now - timedelta(hours=40),
            created_at=now - timedelta(hours=40),
            updated_at=now - timedelta(hours=1),
            discovery_confidence=0,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="operations-heartbeat-newer".ljust(64, "m"),
            summary="Latest heartbeat no longer found a clear source.",
        )
        db.add_all([proposal, manual])
        db.commit()
        proposal_id = proposal.id

    first = client.get("/api/operations/inbox").json()
    assert first["counts_by_type"] == {"TERMS_SOURCE_REQUIRED": 1}
    assert first["items"][0]["entity_id"] != str(proposal_id)

    with SessionLocal() as db:
        proposal = db.get(TermsResearchRun, proposal_id)
        assert proposal is not None
        proposal.updated_at = now
        db.commit()

    second = client.get("/api/operations/inbox").json()
    assert second["items"] == []


def test_terms_retry_warning_includes_latest_error_without_requiring_user() -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Example", website_domain="example.com")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Example Affiliate")
        db.add(program)
        db.flush()
        run = TermsResearchRun(
            program_id=program.id,
            domain="example.com",
            status=ResearchStatus.RETRY_REQUIRED,
            checked_at=datetime.now(UTC),
            discovery_confidence=0,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="terms-actionable-inbox".ljust(64, "x"),
            summary="No source found.",
        )
        db.add(run)
        db.flush()
        db.add(
            AuditLog(
                entity_type="terms_research_run",
                entity_id=str(run.id),
                action=AuditAction.IMPORT,
                actor="official-web-v1",
                payload_json={
                    "collection_errors": [
                        "Tạm thời · https://example.com/affiliate-terms: timed out"
                    ],
                    "priority_source_urls": [
                        "https://example.com/stored-affiliate-policy"
                    ],
                    "permissions_changed": False,
                },
            )
        )
        db.commit()

    body = client.get("/api/operations/inbox").json()
    assert body["counts_by_type"] == {"TERMS_RETRY_PENDING": 1}
    assert body["requires_user_count"] == 0
    assert body["warning_count"] == 1
    item = body["items"][0]
    assert item["program_id"] == program.id
    assert item["action_label"] == "Xem trạng thái"
    assert item["action_view"] == "programs"
    assert item["merchant_domain"] == "example.com"
    assert item["source_url"] == "https://example.com/stored-affiliate-policy"
    assert "timed out" in item["detail"]
    assert "tự thử lại" in item["detail"]
    assert "Đã ưu tiên 1 URL" in item["detail"]
    assert "Dự án vẫn được giữ" in item["detail"]
    assert item["requires_user"] is False
