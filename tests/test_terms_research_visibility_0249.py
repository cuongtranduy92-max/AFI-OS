from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from afi_os.models import Merchant, Program, TermsEvidence, TermsResearchRun

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_data() -> None:
    with SessionLocal() as db:
        for model in (TermsResearchRun, TermsEvidence, Program, Merchant):
            db.execute(delete(model))
        db.commit()


def _program() -> dict:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": "Visibility",
            "website_domain": "visibility.example",
            "program_name": "Visibility Affiliate Program",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _run(
    program_id: int,
    *,
    status: ResearchStatus = ResearchStatus.PROPOSAL_READY,
    checked_at: datetime,
    attempted_at: datetime,
) -> None:
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                program_id=program_id,
                domain="visibility.example",
                fixture_version="visibility-test-v1",
                status=status,
                checked_at=checked_at,
                created_at=checked_at,
                updated_at=attempted_at,
                discovery_confidence=0.9,
                source_urls=["https://visibility.example/affiliate"],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash=f"visibility-{status.value}-{attempted_at.timestamp()}",
                summary="Official pages checked; no public PPC permission found.",
            )
        )
        db.commit()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_program_separates_recent_research_from_missing_permission_evidence() -> None:
    now = datetime.now(UTC)
    program = _program()
    attempted_at = now - timedelta(minutes=20)
    _run(
        program["id"],
        checked_at=now - timedelta(hours=2),
        attempted_at=attempted_at,
    )

    stored = client.get("/api/programs").json()[0]
    assert _parse(stored["last_research_attempted_at"]) == attempted_at
    assert _parse(stored["research_next_due_at"]) == attempted_at + timedelta(hours=24)
    assert stored["research_status"] == "PROPOSAL_READY"
    assert stored["research_is_fresh"] is True
    assert stored["permission_evidence_found"] is False
    assert stored["evidence_count"] == 0
    assert stored["last_terms_checked_at"] is None
    assert stored["evidence_is_stale"] is True
    assert stored["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert stored["paid_search_permission"] == "NOT_CHECKED"
    assert stored["brand_keyword_permission"] == "NOT_CHECKED"
    assert stored["non_brand_permission"] == "NOT_CHECKED"

    inbox = client.get("/api/operations/inbox").json()
    warning = next(
        item
        for item in inbox["items"]
        if item["key"] == f"TERMS_NO_PERMISSION_EVIDENCE:{program['id']}"
    )
    assert warning["item_type"] == "TERMS_PERMISSION_NOT_FOUND"
    assert warning["requires_user"] is False
    assert warning["severity"] == "WARNING"
    assert "PPC vẫn NOT_CHECKED" in warning["detail"]
    assert inbox["requires_user_count"] == 0


def test_existing_permission_evidence_replaces_no_evidence_warning() -> None:
    now = datetime.now(UTC)
    program = _program()
    _run(
        program["id"],
        checked_at=now - timedelta(hours=1),
        attempted_at=now - timedelta(minutes=10),
    )
    with SessionLocal() as db:
        db.add(
            TermsEvidence(
                program_id=program["id"],
                source_url="https://visibility.example/affiliate-terms",
                source_type="AFFILIATE_TERMS_PAGE",
                excerpt="Non-brand paid search is allowed after written approval.",
                evidence_hash="visibility-permission-proposal",
                checked_at=now - timedelta(minutes=30),
                reviewer="visibility-test",
                confidence=0.9,
                decision=PermissionStatus.APPROVAL_REQUIRED,
                scope="PAID_SEARCH",
                applies_to="PAID_SEARCH",
                review_status=EvidenceReviewStatus.PROPOSED,
                source_authority=SourceAuthority.OFFICIAL,
                collected_by="AUTOMATED_WEB",
            )
        )
        db.commit()

    stored = client.get("/api/programs").json()[0]
    assert stored["permission_evidence_found"] is True
    assert stored["evidence_count"] == 1
    keys = {item["key"] for item in client.get("/api/operations/inbox").json()["items"]}
    assert f"TERMS_NO_PERMISSION_EVIDENCE:{program['id']}" not in keys
    assert any(key.startswith("TERMS_EVIDENCE:") for key in keys)
    assert stored["paid_search_permission"] == "NOT_CHECKED"


def test_manual_or_retry_attempt_keeps_existing_action_without_duplicate_warning() -> None:
    now = datetime.now(UTC)
    program = _program()
    _run(
        program["id"],
        status=ResearchStatus.MANUAL_INPUT_REQUIRED,
        checked_at=now - timedelta(hours=1),
        attempted_at=now - timedelta(minutes=5),
    )

    inbox = client.get("/api/operations/inbox").json()
    keys = {item["key"] for item in inbox["items"]}
    assert f"TERMS_NO_PERMISSION_EVIDENCE:{program['id']}" not in keys
    assert "TERMS_MANUAL:visibility.example" in keys
    assert inbox["requires_user_count"] == 1


def test_web_ui_explains_research_and_permission_evidence_separately() -> None:
    script = Path("apps/web/app.js").read_text(encoding="utf-8")
    page = Path("apps/web/index.html").read_text(encoding="utf-8")
    assert "last_research_attempted_at" in script
    assert "Không thấy quyền PPC công khai" in script
    assert "đến hạn rà lại" in script
    assert "Lần rà / bằng chứng" in page
