from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    CommissionType,
    EvidenceReviewStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import AuditLog, CommissionFact, Merchant, Program

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_review_data() -> None:
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        db.execute(delete(CommissionFact))
        db.execute(delete(Program))
        db.execute(delete(Merchant))
        db.commit()


def _program() -> dict:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": "Merchant",
            "website_domain": "merchant.example.org",
            "program_name": "Merchant Affiliate Program",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _fact(
    program_id: int,
    *,
    suffix: str,
    rate: str = "0.30",
    commission_type: CommissionType = CommissionType.RECURRING_LIFETIME,
    confidence: float = 0.90,
    source_url: str = "https://merchant.example.org/affiliate",
) -> int:
    with SessionLocal() as db:
        fact = CommissionFact(
            program_id=program_id,
            scope="COMMISSION",
            source_url=source_url,
            source_authority=SourceAuthority.OFFICIAL,
            excerpt=f"Official commission statement {suffix}",
            checked_at=datetime.now(UTC),
            confidence=confidence,
            commission_type=commission_type,
            commission_rate=Decimal(rate),
            rate_is_maximum=False,
            applies_to=suffix,
            review_status=EvidenceReviewStatus.PROPOSED,
            collected_by="TEST",
            evidence_hash=(suffix * 64)[:64],
        )
        db.add(fact)
        db.commit()
        return fact.id


def _review(program_id: int, fact_id: int, action: str):
    return client.post(
        f"/api/programs/{program_id}/commission-facts/{fact_id}/review",
        json={"action": action, "reviewed_by": "Operator"},
    )


def test_accept_commission_fact_never_changes_ppc_permissions() -> None:
    program = _program()
    fact_id = _fact(program["id"], suffix="lifetime")

    response = _review(program["id"], fact_id, "ACCEPT")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fact"]["review_status"] == "ACCEPTED"
    assert body["commission_state"] == "RESOLVED"
    assert body["permissions_changed"] is False

    current = client.get("/api/programs").json()[0]
    assert current["commission_state"] == "RESOLVED"
    for field in (
        "paid_search_permission",
        "brand_keyword_permission",
        "non_brand_permission",
        "direct_link_permission",
    ):
        assert current[field] == "NOT_CHECKED"
    with SessionLocal() as db:
        audit = db.scalar(
            select(AuditLog).where(AuditLog.entity_type == "commission_fact")
        )
        assert audit is not None
        assert audit.payload_json["permissions_changed"] is False


def test_conflict_remains_until_other_fact_is_rejected() -> None:
    program = _program()
    first = _fact(
        program["id"],
        suffix="first-payment",
        rate="0.40",
        commission_type=CommissionType.ONE_TIME,
    )
    second = _fact(
        program["id"],
        suffix="lifetime",
        rate="0.50",
        commission_type=CommissionType.RECURRING_LIFETIME,
    )

    accepted = _review(program["id"], first, "ACCEPT")
    assert accepted.json()["commission_state"] == "CONFLICT"
    rejected = _review(program["id"], second, "REJECT")
    assert rejected.json()["commission_state"] == "RESOLVED"
    assert rejected.json()["fact"]["review_status"] == "REJECTED"


def test_invalid_commission_fact_cannot_be_accepted_but_can_be_rejected() -> None:
    program = _program()
    low_confidence = _fact(
        program["id"], suffix="low-confidence", confidence=0.50
    )
    blocked = _review(program["id"], low_confidence, "ACCEPT")
    assert blocked.status_code == 422
    assert "Confidence" in blocked.text
    assert _review(program["id"], low_confidence, "REJECT").status_code == 200

    off_domain = _fact(
        program["id"],
        suffix="off-domain",
        source_url="https://unrelated.example/affiliate",
    )
    blocked_source = _review(program["id"], off_domain, "ACCEPT")
    assert blocked_source.status_code == 422
    assert "merchant domain" in blocked_source.text
