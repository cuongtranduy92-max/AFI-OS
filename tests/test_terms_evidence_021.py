from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import PermissionStatus, ResearchStatus
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
from afi_os.schemas import EvidenceInput, ProgramCreate, TermsEvidenceCreate
from afi_os.services import terms_research

client = TestClient(app)

PERMISSION_FIELDS = (
    "paid_search_permission",
    "brand_keyword_permission",
    "non_brand_permission",
    "direct_link_permission",
    "trademark_in_ad_copy_permission",
)


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


def _create_program(domain: str = "example.com", merchant: str = "Example") -> dict:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": merchant,
            "website_domain": domain,
            "program_name": f"{merchant} Affiliate Program",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _post_evidence(
    program_id: int,
    *,
    scope: str,
    decision: str = "NON_BRAND_ONLY",
    confidence: float = 0.95,
    source_authority: str = "OFFICIAL",
    source_url: str = "https://example.com/affiliate-terms",
    excerpt: str | None = None,
) -> dict:
    response = client.post(
        f"/api/programs/{program_id}/evidence",
        json={
            "source_url": source_url,
            "excerpt": excerpt or f"Explicit {scope} policy: {decision}.",
            "checked_at": datetime.now(UTC).isoformat(),
            "reviewer": "Test reviewer",
            "confidence": confidence,
            "decision": decision,
            "scope": scope,
            "source_authority": source_authority,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _review(program_id: int, evidence_id: int, action: str = "ACCEPT"):
    return client.post(
        f"/api/programs/{program_id}/evidence/{evidence_id}/review",
        json={"action": action, "reviewed_by": "Test reviewer"},
    )


def _program(program_id: int) -> dict:
    programs = client.get("/api/programs")
    assert programs.status_code == 200, programs.text
    return next(item for item in programs.json() if item["id"] == program_id)


def _assert_all_permissions(program: dict, expected: str = "NOT_CHECKED") -> None:
    assert {program[field] for field in PERMISSION_FIELDS} == {expected}


def test_schema_and_api_defaults_are_safe() -> None:
    assert (
        ProgramCreate.model_fields["paid_search_permission"].default
        == PermissionStatus.NOT_CHECKED
    )
    assert (
        ProgramCreate.model_fields["brand_keyword_permission"].default
        == PermissionStatus.NOT_CHECKED
    )
    assert (
        ProgramCreate.model_fields["non_brand_permission"].default
        == PermissionStatus.NOT_CHECKED
    )
    assert (
        ProgramCreate.model_fields["direct_link_permission"].default
        == PermissionStatus.NOT_CHECKED
    )
    assert TermsEvidenceCreate.model_fields["decision"].default == PermissionStatus.NOT_CHECKED
    assert TermsEvidenceCreate.model_fields["confidence"].default == 0.0
    assert EvidenceInput.model_fields["decision"].default == PermissionStatus.NOT_CHECKED
    assert EvidenceInput.model_fields["confidence"].default == 0.0

    created = _create_program()
    _assert_all_permissions(created)
    assert created["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    proposed = client.post(
        f"/api/programs/{created['id']}/evidence",
        json={
            "source_url": "https://example.com/affiliate-terms",
            "excerpt": "No explicit PPC permission has been established.",
            "checked_at": datetime.now(UTC).isoformat(),
        },
    )
    assert proposed.status_code == 200, proposed.text
    body = proposed.json()
    assert body["proposal_state"] == "PROPOSED"
    assert body["evidence"]["review_status"] == "PROPOSED"
    assert body["evidence"]["decision"] == "NOT_CHECKED"
    assert body["evidence"]["confidence"] == 0.0
    assert body["evidence"]["source_authority"] == "UNKNOWN"
    assert body["program_gate_status"] == "WARNING_TERMS_UNVERIFIED"
    _assert_all_permissions(_program(created["id"]))


def test_program_api_exposes_safe_signup_source_provenance() -> None:
    official = client.post(
        "/api/programs",
        json={
            "merchant_name": "Merchant",
            "website_domain": "merchant.example",
            "program_name": "Merchant Affiliate Program",
            "signup_url": "https://merchant.example/affiliate",
        },
    )
    assert official.status_code == 200, official.text
    assert official.json()["signup_url"] == "https://merchant.example/affiliate"
    assert official.json()["signup_source_authority"] == "OFFICIAL"

    partner_portal = client.post(
        "/api/programs",
        json={
            "merchant_name": "External Portal Merchant",
            "website_domain": "external-merchant.example",
            "program_name": "External Portal Affiliate Program",
            "signup_url": "https://network.example.net/signup/program-1",
        },
    )
    assert partner_portal.status_code == 200, partner_portal.text
    assert partner_portal.json()["signup_source_authority"] == "PARTNER_PORTAL"

    programs = client.get("/api/programs")
    assert programs.status_code == 200, programs.text
    by_domain = {item["website_domain"]: item for item in programs.json()}
    assert by_domain["merchant.example"]["signup_source_authority"] == "OFFICIAL"
    assert (
        by_domain["external-merchant.example"]["signup_source_authority"]
        == "PARTNER_PORTAL"
    )


def test_program_urls_reject_non_http_schemes() -> None:
    invalid_create = client.post(
        "/api/programs",
        json={
            "merchant_name": "Unsafe",
            "website_domain": "unsafe.example",
            "program_name": "Unsafe Affiliate Program",
            "signup_url": "javascript:alert(1)",
        },
    )
    assert invalid_create.status_code == 422, invalid_create.text

    created = _create_program(domain="safe.example", merchant="Safe")
    invalid_update = client.patch(
        f"/api/programs/{created['id']}",
        json={"dashboard_url": "data:text/html,<script>alert(1)</script>"},
    )
    assert invalid_update.status_code == 422, invalid_update.text


def test_terms_ui_renders_signup_link_through_scheme_guard() -> None:
    script = client.get("/app.js")
    assert script.status_code == 200, script.text
    assert "function safeExternalUrl(url)" in script.text
    assert "function safeExternalLink(url, label)" in script.text
    assert "['http:', 'https:'].includes(parsed.protocol)" in script.text
    assert 'safeExternalLink(item.signup_url, "Mở link đăng ký")' in script.text
    assert "item.signup_source_authority" in script.text
    assert "Chưa có link đăng ký" in script.text


def test_all_dynamic_external_links_use_the_shared_scheme_guard() -> None:
    script = client.get("/app.js")
    assert script.status_code == 200, script.text
    assert script.text.count("<a href=") == 1
    assert '<a href="${esc(parsed.href)}"' in script.text
    assert '<a href="${esc(item.source_url)}"' not in script.text
    assert '<a href="${esc(change.url)}"' not in script.text
    assert "new URL(change.url)" not in script.text
    assert "safeExternalHostLink(change.url)" in script.text
    assert 'safeExternalLink(item.source_url, "Mở nguồn")' in script.text
    assert "safeExternalLink(item.source_url, item.source_name)" in script.text


def test_posted_evidence_is_only_a_proposal_and_does_not_open_permission() -> None:
    created = _create_program()
    proposed = _post_evidence(created["id"], scope="PAID_SEARCH")

    assert proposed["proposal_state"] == "PROPOSED"
    assert proposed["evidence"]["review_status"] == "PROPOSED"
    assert proposed["program_gate_status"] == "WARNING_TERMS_UNVERIFIED"

    stored = _program(created["id"])
    _assert_all_permissions(stored)
    assert stored["evidence_count"] == 1
    assert stored["evidence_proposal_count"] == 1
    assert stored["gate_status"] == "WARNING_TERMS_UNVERIFIED"


def test_unaccepted_duplicate_can_refresh_metadata_without_creating_a_second_row() -> None:
    created = _create_program()
    excerpt = "Paid search is allowed only for non-brand keywords."
    first = _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        confidence=0.0,
        source_authority="UNKNOWN",
        excerpt=excerpt,
    )
    refreshed = _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        confidence=0.95,
        source_authority="OFFICIAL",
        excerpt=excerpt,
    )

    assert refreshed["duplicate"] is True
    assert refreshed["updated"] is True
    assert refreshed["evidence"]["id"] == first["evidence"]["id"]
    assert refreshed["evidence"]["source_authority"] == "OFFICIAL"
    assert refreshed["evidence"]["confidence"] == 0.95
    assert len(client.get(f"/api/programs/{created['id']}/evidence").json()) == 1

    reviewed = _review(created["id"], refreshed["evidence"]["id"])
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["resolved_permission"] == "NON_BRAND_ONLY"


@pytest.mark.parametrize(
    ("confidence", "source_authority", "scope"),
    [
        (0.79, "OFFICIAL", "PAID_SEARCH"),
        (0.99, "UNKNOWN", "NON_BRAND"),
    ],
)
def test_low_confidence_or_unknown_source_cannot_be_accepted(
    confidence: float,
    source_authority: str,
    scope: str,
) -> None:
    created = _create_program()
    proposed = _post_evidence(
        created["id"],
        scope=scope,
        confidence=confidence,
        source_authority=source_authority,
        excerpt=f"Candidate evidence for {scope} with {source_authority} authority.",
    )

    reviewed = _review(created["id"], proposed["evidence"]["id"])
    assert reviewed.status_code == 422, reviewed.text

    evidence = client.get(f"/api/programs/{created['id']}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()[0]["review_status"] == "PROPOSED"
    _assert_all_permissions(_program(created["id"]))


def test_ready_gate_requires_accepted_official_paid_search_and_non_brand_evidence() -> None:
    created = _create_program()
    paid = _post_evidence(created["id"], scope="PAID_SEARCH")
    non_brand = _post_evidence(created["id"], scope="NON_BRAND")

    assert _program(created["id"])["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    accepted_paid = _review(created["id"], paid["evidence"]["id"])
    assert accepted_paid.status_code == 200, accepted_paid.text
    assert accepted_paid.json()["resolved_permission"] == "NON_BRAND_ONLY"
    assert accepted_paid.json()["program_gate_status"] == "WARNING_TERMS_UNVERIFIED"

    half_resolved = _program(created["id"])
    assert half_resolved["paid_search_permission"] == "NON_BRAND_ONLY"
    assert half_resolved["non_brand_permission"] == "NOT_CHECKED"

    accepted_non_brand = _review(created["id"], non_brand["evidence"]["id"])
    assert accepted_non_brand.status_code == 200, accepted_non_brand.text
    assert accepted_non_brand.json()["resolved_permission"] == "NON_BRAND_ONLY"
    assert accepted_non_brand.json()["program_gate_status"] == "TERMS_OK"

    ready = _program(created["id"])
    assert ready["paid_search_permission"] == "NON_BRAND_ONLY"
    assert ready["non_brand_permission"] == "NON_BRAND_ONLY"
    assert ready["gate_status"] == "TERMS_OK"


def test_new_official_proposal_conflicting_with_accepted_evidence_removes_green_state() -> None:
    created = _create_program()
    paid = _post_evidence(created["id"], scope="PAID_SEARCH")
    non_brand = _post_evidence(created["id"], scope="NON_BRAND")
    assert _review(created["id"], paid["evidence"]["id"]).status_code == 200
    assert _review(created["id"], non_brand["evidence"]["id"]).status_code == 200
    assert _program(created["id"])["gate_status"] == "TERMS_OK"

    changed_source = _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        decision="PROHIBITED",
        source_url="https://example.com/affiliate-terms/updated-ppc-policy",
        excerpt="Updated official policy: affiliates may not use paid search.",
    )
    assert changed_source["proposal_state"] == "PROPOSED"
    assert changed_source["program_gate_status"] == "WARNING_TERMS_CONFLICT"

    warning = _program(created["id"])
    assert warning["paid_search_permission"] == "NON_BRAND_ONLY"
    assert warning["non_brand_permission"] == "NON_BRAND_ONLY"
    assert warning["gate_status"] == "WARNING_TERMS_CONFLICT"

    rejected = _review(
        created["id"], changed_source["evidence"]["id"], action="REJECT"
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["resolved_permission"] == "NON_BRAND_ONLY"
    assert rejected.json()["program_gate_status"] == "TERMS_OK"


def test_conflicting_unreviewed_official_proposals_are_warning_only() -> None:
    created = _create_program()
    _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        decision="NON_BRAND_ONLY",
        source_url="https://example.com/affiliate-terms/allowed",
    )
    _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        decision="PROHIBITED",
        source_url="https://example.com/affiliate-terms/prohibited",
    )

    warning = _program(created["id"])
    _assert_all_permissions(warning)
    assert warning["gate_status"] == "WARNING_TERMS_CONFLICT"


def test_compliance_endpoint_ignores_forged_fields_and_uses_stored_accepted_evidence() -> None:
    created = _create_program()
    forged = client.post(
        "/api/compliance/evaluate",
        json={
            "program_id": created["id"],
            "paid_search_permission": "BRAND_ALLOWED",
            "brand_keyword_permission": "BRAND_ALLOWED",
            "non_brand_permission": "BRAND_ALLOWED",
            "evidence": [
                {
                    "decision": "BRAND_ALLOWED",
                    "checked_at": datetime.now(UTC).isoformat(),
                    "confidence": 1,
                }
            ],
        },
    )
    assert forged.status_code == 200, forged.text
    assert forged.json()["allowed"] is False
    assert forged.json()["status"] == "WARNING_TERMS_UNVERIFIED"

    paid = _post_evidence(created["id"], scope="PAID_SEARCH")
    non_brand = _post_evidence(created["id"], scope="NON_BRAND")
    proposed_only = client.post(
        "/api/compliance/evaluate",
        json={"program_id": created["id"]},
    )
    assert proposed_only.status_code == 200, proposed_only.text
    assert proposed_only.json()["allowed"] is False

    assert _review(created["id"], paid["evidence"]["id"]).status_code == 200
    assert _review(created["id"], non_brand["evidence"]["id"]).status_code == 200
    accepted = client.post(
        "/api/compliance/evaluate",
        json={"program_id": created["id"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {
        "allowed": True,
        "status": "TERMS_OK",
        "reasons": [],
        "project_included": True,
        "warning_only": True,
    }


@pytest.mark.parametrize(
    ("action", "expected_reviewed_permission"),
    [("ACCEPT", "NON_BRAND_ONLY"), ("REJECT", "NOT_CHECKED")],
)
def test_review_preserves_unrelated_migrated_legacy_permissions(
    action: str,
    expected_reviewed_permission: str,
) -> None:
    legacy_checked_at = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    created_response = client.post(
        "/api/programs",
        json={
            "merchant_name": "Legacy Merchant",
            "website_domain": "example.com",
            "program_name": "Legacy Affiliate Program",
            "paid_search_permission": "BRAND_ALLOWED",
            "brand_keyword_permission": "BRAND_ALLOWED",
            "non_brand_permission": "NON_BRAND_ONLY",
            "direct_link_permission": "BRAND_ALLOWED",
            "trademark_in_ad_copy_permission": "BRAND_ALLOWED",
        },
    )
    assert created_response.status_code == 200, created_response.text
    created = created_response.json()
    assert created["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    with SessionLocal() as db:
        migrated = db.get(Program, created["id"])
        assert migrated is not None
        migrated.last_terms_checked_at = legacy_checked_at
        db.commit()

    proposed = _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        decision="NON_BRAND_ONLY",
        excerpt="Paid search is allowed only for non-brand keywords.",
    )
    reviewed = _review(created["id"], proposed["evidence"]["id"], action=action)
    assert reviewed.status_code == 200, reviewed.text

    stored = _program(created["id"])
    assert stored["paid_search_permission"] == expected_reviewed_permission
    assert stored["brand_keyword_permission"] == "BRAND_ALLOWED"
    assert stored["non_brand_permission"] == "NON_BRAND_ONLY"
    assert stored["direct_link_permission"] == "BRAND_ALLOWED"
    assert stored["trademark_in_ad_copy_permission"] == "BRAND_ALLOWED"
    assert stored["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    stored_checked_at = datetime.fromisoformat(stored["last_terms_checked_at"])
    if stored_checked_at.tzinfo is None:
        stored_checked_at = stored_checked_at.replace(tzinfo=UTC)
    if action == "ACCEPT":
        evidence_checked_at = datetime.fromisoformat(proposed["evidence"]["checked_at"])
        if evidence_checked_at.tzinfo is None:
            evidence_checked_at = evidence_checked_at.replace(tzinfo=UTC)
        assert stored_checked_at == evidence_checked_at
    else:
        assert stored_checked_at == legacy_checked_at


def test_contradictory_accepted_official_evidence_resolves_to_conflict() -> None:
    created = _create_program()
    allowed = _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        decision="NON_BRAND_ONLY",
        source_url="https://example.com/affiliate-terms/paid-search",
        excerpt="Paid search is allowed only for non-brand keywords.",
    )
    prohibited = _post_evidence(
        created["id"],
        scope="PAID_SEARCH",
        decision="PROHIBITED",
        source_url="https://example.com/affiliate-terms/ppc-policy",
        excerpt="Affiliates may not use paid search advertising.",
    )

    first_review = _review(created["id"], allowed["evidence"]["id"])
    assert first_review.status_code == 200, first_review.text
    assert first_review.json()["resolved_permission"] == "NON_BRAND_ONLY"

    conflict_review = _review(created["id"], prohibited["evidence"]["id"])
    assert conflict_review.status_code == 200, conflict_review.text
    assert conflict_review.json()["resolved_permission"] == "CONFLICT"
    assert conflict_review.json()["program_gate_status"] == "WARNING_TERMS_CONFLICT"

    conflicted = _program(created["id"])
    assert conflicted["paid_search_permission"] == "CONFLICT"
    assert conflicted["gate_status"] == "WARNING_TERMS_CONFLICT"


def test_pictory_fixture_seeds_once_then_recheck_uses_live_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _create_program(domain="pictory.ai", merchant="Pictory")
    before = {field: existing[field] for field in PERMISSION_FIELDS}

    first = client.post("/api/programs/research", json={"domain": "https://pictory.ai"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["domain"] == "pictory.ai"
    assert body["program_id"] == existing["id"]
    assert body["status"] == "CONFLICT"
    assert body["commission_state"] == "CONFLICT"
    assert body["imported_commission_facts"] == 2
    assert body["duplicate_commission_facts"] == 0
    assert body["duplicate_run"] is False
    assert len(body["commission_facts"]) == 2
    assert {item["commission_type"] for item in body["commission_facts"]} == {
        "ONE_TIME",
        "RECURRING_UNSPECIFIED",
    }
    assert all(item["review_status"] == "PROPOSED" for item in body["commission_facts"])
    assert all(item["decision"] == "NOT_CHECKED" for item in body["permission_proposals"])
    assert all(item["confidence"] == 0.0 for item in body["permission_proposals"])
    assert body["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    after_first = _program(existing["id"])
    assert {field: after_first[field] for field in PERMISSION_FIELDS} == before
    assert after_first["commission_fact_count"] == 2
    assert after_first["commission_state"] == "CONFLICT"
    assert after_first["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    with SessionLocal() as db:
        first_run = db.scalar(
            select(TermsResearchRun).where(TermsResearchRun.domain == "pictory.ai")
        )
        assert first_run is not None
        source_checked_at = first_run.checked_at
        first_heartbeat = first_run.updated_at

    captured: dict[str, list[str]] = {}

    def unavailable_live_sources(_domain: str, *, priority_urls=()):
        captured["priority_urls"] = list(priority_urls)
        return [], [
            f"{terms_research.RETRYABLE_ERROR_PREFIX}simulated live source outage"
        ]

    monkeypatch.setattr(
        "afi_os.services.terms_research.discover_official_pages",
        unavailable_live_sources,
    )
    second = client.post("/api/programs/research", json={"domain": "pictory.ai"})
    assert second.status_code == 200, second.text
    repeated = second.json()
    assert repeated["status"] == "RETRY_REQUIRED"
    assert repeated["imported_commission_facts"] == 0
    assert repeated["duplicate_commission_facts"] == 0
    assert repeated["duplicate_run"] is False
    assert repeated["commission_facts"] == []
    assert {
        "https://partners.pictory.ai/signup/40690",
        "https://pictory.ai/partnernow",
    }.issubset(set(captured["priority_urls"]))

    with SessionLocal() as db:
        fact_count = db.scalar(
            select(func.count()).select_from(CommissionFact).where(
                CommissionFact.program_id == existing["id"]
            )
        )
        runs = db.scalars(
            select(TermsResearchRun)
            .where(TermsResearchRun.domain == "pictory.ai")
            .order_by(TermsResearchRun.id.asc())
        ).all()
        live_failure_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "terms_research_run",
                AuditLog.entity_id == str(runs[-1].id),
                AuditLog.actor == "official-web-v9",
            )
        )
    assert fact_count == 2
    assert len(runs) == 2
    assert runs[0].checked_at == source_checked_at
    assert runs[0].updated_at == first_heartbeat
    assert runs[1].fixture_version == "official-web-v9"
    assert runs[1].status == ResearchStatus.RETRY_REQUIRED
    assert live_failure_audit is not None
    assert live_failure_audit.payload_json["duplicate_run"] is False
    assert live_failure_audit.payload_json["permissions_changed"] is False
    assert {
        "https://partners.pictory.ai/signup/40690",
        "https://pictory.ai/partnernow",
    }.issubset(set(live_failure_audit.payload_json["priority_source_urls"]))

    attempts_response = client.get(
        f"/api/programs/{existing['id']}/research-attempts"
    )
    assert attempts_response.status_code == 200, attempts_response.text
    attempts = attempts_response.json()
    assert len(attempts) == 2
    assert attempts[0]["run_id"] == runs[1].id
    assert attempts[0]["status"] == "RETRY_REQUIRED"
    assert attempts[0]["duplicate_run"] is False
    assert attempts[0]["collection_errors"] == [
        f"{terms_research.RETRYABLE_ERROR_PREFIX}simulated live source outage"
    ]
    assert attempts[0]["permissions_changed"] is False
    assert attempts[0]["imported_terms_evidence"] == 0
    assert attempts[0]["refreshed_terms_evidence"] == 0
    assert attempts[0]["imported_commission_facts"] == 0
    assert attempts[0]["refreshed_commission_facts"] == 0
    assert {
        "https://partners.pictory.ai/signup/40690",
        "https://pictory.ai/partnernow",
    }.issubset(set(attempts[0]["priority_source_urls"]))
    assert attempts[1]["imported_commission_facts"] == 2
    assert attempts[1]["refreshed_commission_facts"] == 0
    _assert_all_permissions(_program(existing["id"]))


def test_reserved_domain_returns_manual_input_without_opening_permissions() -> None:
    response = client.post(
        "/api/programs/research",
        json={"domain": "https://www.unverified-example.test/affiliate"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "unverified-example.test"
    assert body["status"] == "MANUAL_INPUT_REQUIRED"
    assert body["program_id"] is None
    assert body["discovery_confidence"] == 0.0
    assert body["source_urls"] == []
    assert body["permission_proposals"] == []
    assert body["commission_state"] == "NOT_CHECKED"
    assert body["commission_facts"] == []
    assert body["imported_commission_facts"] == 0
    assert body["duplicate_commission_facts"] == 0
    assert body["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert client.get("/api/programs").json() == []

    repeated = client.post(
        "/api/programs/research",
        json={"domain": "unverified-example.test"},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["duplicate_run"] is True
    with SessionLocal() as db:
        audits = db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "terms_research_run")
            .order_by(AuditLog.id.asc())
        ).all()
    assert len(audits) == 2
    assert audits[0].payload_json["duplicate_run"] is False
    assert audits[1].payload_json["duplicate_run"] is True
    assert all(item.payload_json["permissions_changed"] is False for item in audits)
