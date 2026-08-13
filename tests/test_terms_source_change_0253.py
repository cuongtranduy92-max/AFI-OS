from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    EvidenceReviewStatus,
    PermissionStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import AuditLog, Merchant, Program, TermsEvidence
from afi_os.services import terms_research
from afi_os.services.operations import operations_inbox

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program(domain: str) -> int:
    with SessionLocal() as db:
        merchant = Merchant(name=domain, website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name=f"{domain} Affiliate")
        db.add(program)
        db.commit()
        db.refresh(program)
        return program.id


def _page(url: str, text: str) -> dict:
    return {"url": url, "title": "Affiliate policy", "text": text, "links": []}


def _collect(domain: str, pages: list[dict], errors: list[str] | None = None) -> dict:
    with SessionLocal() as db:
        return terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (pages, errors or []),
        )


def test_policy_content_change_is_hashed_audited_and_warning_only() -> None:
    domain = "source-change.example.org"
    program_id = _program(domain)
    url = f"https://{domain}/affiliate-policy"

    first = _collect(
        domain,
        [_page(url, "Affiliate partners must read this policy before publishing links.")],
    )
    second = _collect(
        domain,
        [_page(url, "Affiliate partners must read this revised policy before publishing links.")],
    )

    assert first["source_change_status"] == "INITIAL"
    assert second["source_change_status"] == "CHANGED"
    assert second["source_changes"] == [
        {"url": url, "change_type": "CONTENT_CHANGED"}
    ]
    assert second["duplicate_run"] is True

    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
        assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
        assert program.non_brand_permission == PermissionStatus.NOT_CHECKED
        assert program.direct_link_permission == PermissionStatus.NOT_CHECKED
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.entity_type == "terms_research_run")
            .order_by(AuditLog.id.desc())
        )
        assert audit is not None
        snapshots = audit.payload_json["source_snapshots"]
        assert len(snapshots[0]["content_sha256"]) == 64
        assert "revised policy" not in json.dumps(snapshots)
        inbox = operations_inbox(db)

    item = next(item for item in inbox["items"] if item["program_id"] == program_id)
    assert "nguồn Terms thay đổi" in item["title"]
    assert "PPC, dự án và campaign không bị thay đổi" in item["detail"]

    attempts = client.get(f"/api/programs/{program_id}/research-attempts").json()
    assert attempts[0]["source_change_status"] == "CHANGED"
    assert attempts[0]["source_changes"] == second["source_changes"]


def test_unrelated_footer_change_does_not_trigger_policy_warning() -> None:
    domain = "stable-source.example.org"
    _program(domain)
    url = f"https://{domain}/affiliate-policy"
    _collect(
        domain,
        [_page(url, "Affiliate partners must read this policy. Copyright 2025.")],
    )
    second = _collect(
        domain,
        [_page(url, "Affiliate partners must read this policy. Copyright 2026.")],
    )

    assert second["source_change_status"] == "UNCHANGED"
    assert second["source_changes"] == []


def test_added_and_removed_sources_are_reported_deterministically() -> None:
    domain = "source-set.example.org"
    _program(domain)
    first_url = f"https://{domain}/affiliate-old"
    kept_url = f"https://{domain}/affiliate-current"
    added_url = f"https://{domain}/partner-policy"
    _collect(
        domain,
        [
            _page(first_url, "Affiliate publisher policy overview."),
            _page(kept_url, "Affiliate partner policy overview."),
        ],
    )
    second = _collect(
        domain,
        [
            _page(kept_url, "Affiliate partner policy overview."),
            _page(added_url, "Partner referral policy overview."),
        ],
    )

    assert second["source_change_status"] == "CHANGED"
    assert second["source_changes"] == [
        {"url": added_url, "change_type": "ADDED"},
        {"url": first_url, "change_type": "REMOVED"},
    ]


def test_total_temporary_fetch_failure_does_not_claim_source_removal() -> None:
    domain = "temporary-source.example.org"
    _program(domain)
    url = f"https://{domain}/affiliate-policy"
    _collect(domain, [_page(url, "Affiliate partner policy overview.")])
    second = _collect(
        domain,
        [],
        [f"{terms_research.RETRYABLE_ERROR_PREFIX}{url}: timed out"],
    )

    assert second["source_change_status"] == "UNAVAILABLE"
    assert second["source_changes"] == []


def test_changed_source_with_existing_evidence_gets_standalone_tracking_warning() -> None:
    domain = "accepted-source.example.org"
    program_id = _program(domain)
    url = f"https://{domain}/affiliate-program"
    with SessionLocal() as db:
        db.add(
            TermsEvidence(
                program_id=program_id,
                source_url=f"https://{domain}/affiliate-terms",
                excerpt="Paid search is prohibited.",
                evidence_hash="accepted-source-change".ljust(64, "a"),
                checked_at=datetime.now(UTC),
                reviewer="operator",
                confidence=0.95,
                decision=PermissionStatus.PROHIBITED,
                scope="PAID_SEARCH",
                applies_to="PAID_SEARCH",
                review_status=EvidenceReviewStatus.ACCEPTED,
                source_authority=SourceAuthority.OFFICIAL,
            )
        )
        db.commit()

    _collect(domain, [_page(url, "Earn a 25% lifetime recurring commission.")])
    _collect(domain, [_page(url, "Earn a 30% lifetime recurring commission.")])

    with SessionLocal() as db:
        inbox = operations_inbox(db)
        program = db.get(Program, program_id)
        assert program is not None
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED

    warning = next(
        item
        for item in inbox["items"]
        if item["key"] == f"TERMS_SOURCE_CHANGED:{program_id}"
    )
    assert warning["requires_user"] is False
    assert warning["severity"] == "WARNING"
    assert warning["item_type"] == "TERMS_SOURCE_CHANGED"
