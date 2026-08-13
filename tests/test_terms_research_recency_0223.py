from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

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
    AffiliateNetwork,
    AuditLog,
    Campaign,
    CampaignDailyStat,
    CampaignProgramLink,
    CommissionFact,
    Merchant,
    Program,
    Spend,
    SyncRun,
    TermsEvidence,
    TermsResearchRun,
)

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_data() -> None:
    with SessionLocal() as db:
        for model in (
            AuditLog,
            SyncRun,
            CampaignDailyStat,
            Spend,
            CampaignProgramLink,
            Campaign,
            AdsAccount,
            TermsResearchRun,
            CommissionFact,
            TermsEvidence,
            Program,
            Merchant,
            AffiliateNetwork,
        ):
            db.execute(delete(model))
        db.commit()


def _ready_program(*, reviewed_at: datetime) -> int:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": "Source Watch",
            "website_domain": "source-watch.example",
            "program_name": "Source Watch Affiliate Program",
        },
    )
    assert response.status_code == 200, response.text
    program_id = response.json()["id"]
    checked_at = reviewed_at - timedelta(hours=1)
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        program.paid_search_permission = PermissionStatus.NON_BRAND_ONLY
        program.non_brand_permission = PermissionStatus.NON_BRAND_ONLY
        program.last_terms_checked_at = checked_at
        for scope in ("PAID_SEARCH", "NON_BRAND"):
            db.add(
                TermsEvidence(
                    program_id=program_id,
                    source_url=(
                        f"https://source-watch.example/affiliate-terms/{scope.lower()}"
                    ),
                    excerpt=f"Explicit non-brand permission for {scope}.",
                    evidence_hash=f"accepted-{program_id}-{scope}",
                    checked_at=checked_at,
                    created_at=checked_at,
                    updated_at=reviewed_at,
                    reviewer="Regression test",
                    confidence=0.95,
                    decision=PermissionStatus.NON_BRAND_ONLY,
                    scope=scope,
                    applies_to=scope,
                    review_status=EvidenceReviewStatus.ACCEPTED,
                    source_authority=SourceAuthority.OFFICIAL,
                    collected_by="TEST",
                    reviewed_at=reviewed_at,
                    reviewed_by="Regression test",
                )
            )
        db.commit()
    return program_id


def _research_run(
    program_id: int,
    *,
    status: ResearchStatus,
    checked_at: datetime,
    updated_at: datetime | None = None,
    permission_proposals: list[dict] | None = None,
    suffix: str,
) -> None:
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                program_id=program_id,
                domain="source-watch.example",
                fixture_version="recency-test-v1",
                status=status,
                checked_at=checked_at,
                created_at=checked_at,
                updated_at=updated_at or checked_at,
                discovery_confidence=(
                    0.0
                    if status
                    in {
                        ResearchStatus.MANUAL_INPUT_REQUIRED,
                        ResearchStatus.RETRY_REQUIRED,
                    }
                    else 0.95
                ),
                source_urls=[],
                permission_proposals=permission_proposals or [],
                imported_fact_ids=[],
                run_hash=f"research-{program_id}-{suffix}",
                summary="Recency regression fixture.",
            )
        )
        db.commit()


def _program(program_id: int) -> dict:
    response = client.get("/api/programs")
    assert response.status_code == 200, response.text
    return next(item for item in response.json() if item["id"] == program_id)


def test_newer_source_loss_removes_green_but_keeps_program_and_permissions() -> None:
    now = datetime.now(UTC)
    program_id = _ready_program(reviewed_at=now - timedelta(days=2))
    _research_run(
        program_id,
        status=ResearchStatus.MANUAL_INPUT_REQUIRED,
        checked_at=now - timedelta(days=3),
        updated_at=now - timedelta(hours=1),
        suffix="manual-heartbeat",
    )

    program = _program(program_id)
    assert program["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert program["paid_search_permission"] == "NON_BRAND_ONLY"
    assert program["non_brand_permission"] == "NON_BRAND_ONLY"

    dashboard = client.get("/api/dashboard/summary").json()
    assert dashboard["programs_terms_ok"] == 0
    assert dashboard["programs_with_terms_warnings"] == 1

    compliance = client.post(
        "/api/compliance/evaluate", json={"program_id": program_id}
    )
    assert compliance.status_code == 200, compliance.text
    assert compliance.json()["allowed"] is False
    assert compliance.json()["status"] == "WARNING_TERMS_UNVERIFIED"
    assert compliance.json()["project_included"] is True
    assert compliance.json()["warning_only"] is True

    imported = client.post(
        "/api/exposure/google-ads-import/commit",
        data={
            "source": "GOOGLE_ADS_CSV",
            "account_external_id": "source-watch-account",
            "account_name": "Source Watch Ads",
            "default_program_id": str(program_id),
        },
        files={
            "file": (
                "campaigns.csv",
                (
                    "Date,Campaign ID,Campaign,Campaign status,Campaign type,"
                    "Currency code,Cost,Impressions,Clicks,Conversions\n"
                    "2026-08-10,recency-1,Source Watch Search,ENABLED,Search,"
                    "USD,10,100,10,1\n"
                ).encode(),
                "text/csv",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    exposure = client.get("/api/exposure/summary").json()
    assert exposure["campaigns"][0]["terms_warning_status"] == (
        "WARNING_TERMS_UNVERIFIED"
    )
    assert exposure["campaigns"][0]["project_included"] is True


def test_temporary_source_failure_warns_without_erasing_permissions() -> None:
    now = datetime.now(UTC)
    program_id = _ready_program(reviewed_at=now - timedelta(days=2))
    _research_run(
        program_id,
        status=ResearchStatus.RETRY_REQUIRED,
        checked_at=now - timedelta(hours=1),
        suffix="temporary-retry",
    )

    program = _program(program_id)
    assert program["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert program["paid_search_permission"] == "NON_BRAND_ONLY"
    assert program["non_brand_permission"] == "NON_BRAND_ONLY"


def test_later_successful_research_restores_evidence_backed_green() -> None:
    now = datetime.now(UTC)
    program_id = _ready_program(reviewed_at=now - timedelta(days=2))
    _research_run(
        program_id,
        status=ResearchStatus.MANUAL_INPUT_REQUIRED,
        checked_at=now - timedelta(hours=2),
        suffix="manual",
    )
    assert _program(program_id)["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    _research_run(
        program_id,
        status=ResearchStatus.PROPOSAL_READY,
        checked_at=now - timedelta(hours=1),
        permission_proposals=[
            {
                "scope": scope,
                "decision": "NON_BRAND_ONLY",
                "confidence": 0.95,
            }
            for scope in ("PAID_SEARCH", "NON_BRAND")
        ],
        suffix="success",
    )

    assert _program(program_id)["gate_status"] == "TERMS_OK"
    assert client.get("/api/dashboard/summary").json()["programs_terms_ok"] == 1
    assert client.post(
        "/api/compliance/evaluate", json={"program_id": program_id}
    ).json()["allowed"] is True


def test_commission_only_success_cannot_hide_lost_permission_sources() -> None:
    now = datetime.now(UTC)
    program_id = _ready_program(reviewed_at=now - timedelta(days=2))
    _research_run(
        program_id,
        status=ResearchStatus.PROPOSAL_READY,
        checked_at=now - timedelta(hours=1),
        permission_proposals=[],
        suffix="commission-only",
    )

    warning = _program(program_id)
    assert warning["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert warning["paid_search_permission"] == "NON_BRAND_ONLY"
    assert warning["non_brand_permission"] == "NON_BRAND_ONLY"


def test_human_review_after_source_loss_is_an_intentional_override() -> None:
    now = datetime.now(UTC)
    program_id = _ready_program(reviewed_at=now - timedelta(hours=1))
    _research_run(
        program_id,
        status=ResearchStatus.MANUAL_INPUT_REQUIRED,
        checked_at=now - timedelta(days=1),
        suffix="manual-before-review",
    )

    assert _program(program_id)["gate_status"] == "TERMS_OK"
