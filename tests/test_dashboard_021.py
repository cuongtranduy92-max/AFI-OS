from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from afi_os.db import Base, SessionLocal, engine
from afi_os.main import app
from afi_os.models import (
    AffiliateNetwork,
    AuditLog,
    CommissionFact,
    Merchant,
    Program,
    TermsEvidence,
    TermsResearchRun,
)

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_program_governance_data() -> None:
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        db.execute(delete(TermsResearchRun))
        db.execute(delete(CommissionFact))
        db.execute(delete(TermsEvidence))
        db.execute(delete(Program))
        db.execute(delete(Merchant))
        db.execute(delete(AffiliateNetwork))
        db.commit()


def _create_program(domain: str, name: str, **permissions: str) -> dict:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": name,
            "website_domain": domain,
            "program_name": f"{name} Affiliate Program",
            **permissions,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _accept_non_brand_gate(program: dict) -> None:
    for scope in ("PAID_SEARCH", "NON_BRAND"):
        proposed = client.post(
            f"/api/programs/{program['id']}/evidence",
            json={
                "source_url": (
                    f"https://{program['website_domain']}/affiliate-terms/{scope.lower()}"
                ),
                "excerpt": f"Explicit permission for {scope} non-brand advertising.",
                "checked_at": datetime.now(UTC).isoformat(),
                "reviewer": "Dashboard regression",
                "confidence": 0.95,
                "decision": "NON_BRAND_ONLY",
                "scope": scope,
                "source_authority": "OFFICIAL",
            },
        )
        assert proposed.status_code == 200, proposed.text
        reviewed = client.post(
            f"/api/programs/{program['id']}/evidence/"
            f"{proposed.json()['evidence']['id']}/review",
            json={"action": "ACCEPT", "reviewed_by": "Dashboard regression"},
        )
        assert reviewed.status_code == 200, reviewed.text


def test_dashboard_counts_only_evidence_backed_ready_programs_as_allowed() -> None:
    legacy_positive = _create_program(
        "legacy-positive.example",
        "Legacy Positive",
        paid_search_permission="NON_BRAND_ONLY",
        non_brand_permission="NON_BRAND_ONLY",
    )
    assert legacy_positive["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    patched_positive = _create_program("patched-positive.example", "Patched Positive")
    patched = client.patch(
        f"/api/programs/{patched_positive['id']}",
        json={
            "paid_search_permission": "BRAND_ALLOWED",
            "brand_keyword_permission": "BRAND_ALLOWED",
            "non_brand_permission": "BRAND_ALLOWED",
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    evidence_backed = _create_program("evidence-backed.example", "Evidence Backed")
    _accept_non_brand_gate(evidence_backed)

    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["programs"] == 3
    assert body["programs_explicitly_allowed"] == 1
    assert body["programs_blocked_pending_evidence"] == 2
