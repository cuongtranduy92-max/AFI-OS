from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    CommissionType,
    EvidenceReviewStatus,
    PermissionStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import (
    AuditLog,
    CommissionFact,
    Merchant,
    Program,
    TermsEvidence,
    TermsResearchRun,
)
from afi_os.services import terms_research

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_terms_data() -> None:
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        db.execute(delete(TermsResearchRun))
        db.execute(delete(CommissionFact))
        db.execute(delete(TermsEvidence))
        db.execute(delete(Program))
        db.execute(delete(Merchant))
        db.commit()


def _official_pages(_domain: str, **_kwargs):
    return (
        [
            {
                "url": "https://merchant.example.org/affiliate-terms",
                "title": "Affiliate Program Terms",
                "text": (
                    "Affiliates may not bid on trademark keywords. "
                    "Non-brand generic keywords are allowed for paid search. "
                    "Direct linking from PPC ads is not permitted. "
                    "Approved partners earn a recurring commission of 30%."
                ),
                "links": [],
            }
        ],
        [],
    )


def test_generic_collector_creates_sourced_proposals_but_opens_no_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terms_research, "discover_official_pages", _official_pages)

    response = client.post(
        "/api/programs/research", json={"domain": "merchant.example.org"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PROPOSAL_READY"
    assert body["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert body["imported_terms_evidence"] == 4
    assert body["duplicate_terms_evidence"] == 0
    assert body["commission_state"] == "PROPOSED"
    assert len(body["commission_facts"]) == 1
    assert body["commission_facts"][0]["commission_rate"] == "0.300000"
    assert body["commission_facts"][0]["commission_type"] == "RECURRING_UNSPECIFIED"
    assert all(item["review_status"] == "PROPOSED" for item in body["terms_evidence"])
    assert all(item["source_authority"] == "OFFICIAL" for item in body["terms_evidence"])
    assert all(item["collected_by"] == "AUTOMATED_WEB" for item in body["terms_evidence"])
    assert {
        (item["scope"], item["decision"])
        for item in body["terms_evidence"]
    } == {
        ("BRAND_KEYWORD", "PROHIBITED"),
        ("PAID_SEARCH", "NON_BRAND_ONLY"),
        ("NON_BRAND", "NON_BRAND_ONLY"),
        ("DIRECT_LINK", "PROHIBITED"),
    }

    program = next(
        item for item in client.get("/api/programs").json() if item["id"] == body["program_id"]
    )
    for field in (
        "paid_search_permission",
        "brand_keyword_permission",
        "non_brand_permission",
        "direct_link_permission",
        "trademark_in_ad_copy_permission",
    ):
        assert program[field] == "NOT_CHECKED"


def test_clear_no_evidence_result_still_requests_manual_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: ([], []),
    )

    response = client.post(
        "/api/programs/research", json={"domain": "no-policy.example.org"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "MANUAL_INPUT_REQUIRED"
    assert body["collection_errors"] == []
    assert body["permission_proposals"] == []

    inbox = client.get("/api/operations/inbox").json()
    assert inbox["counts_by_type"] == {"TERMS_SOURCE_REQUIRED": 1}
    assert inbox["requires_user_count"] == 1


def test_permanent_404_misses_do_not_schedule_endless_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: (
            [],
            ["https://merchant.example.org/affiliate-terms: HTTP Error 404"],
        ),
    )

    body = client.post(
        "/api/programs/research", json={"domain": "merchant.example.org"}
    ).json()
    assert body["status"] == "MANUAL_INPUT_REQUIRED"
    assert body["collection_errors"] == [
        "https://merchant.example.org/affiliate-terms: HTTP Error 404"
    ]


def test_generic_collection_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(terms_research, "discover_official_pages", _official_pages)

    first = client.post(
        "/api/programs/research", json={"domain": "merchant.example.org"}
    ).json()
    with SessionLocal() as db:
        first_run = db.scalar(select(TermsResearchRun))
        assert first_run is not None
        source_checked_at = first_run.checked_at
        first_heartbeat = first_run.updated_at
    second = client.post(
        "/api/programs/research", json={"domain": "merchant.example.org"}
    ).json()

    assert first["duplicate_run"] is False
    assert second["duplicate_run"] is True
    assert second["imported_terms_evidence"] == 0
    assert second["duplicate_terms_evidence"] == len(first["terms_evidence"])
    assert second["refreshed_terms_evidence"] == len(first["terms_evidence"])
    assert second["imported_commission_facts"] == 0
    assert second["duplicate_commission_facts"] == 1
    assert second["refreshed_commission_facts"] == 1
    attempts = client.get(
        f"/api/programs/{first['program_id']}/research-attempts"
    ).json()
    assert [item["duplicate_run"] for item in attempts[:2]] == [True, False]
    with SessionLocal() as db:
        assert len(db.scalars(select(Program)).all()) == 1
        assert len(db.scalars(select(TermsEvidence)).all()) == len(first["terms_evidence"])
        facts = db.scalars(select(CommissionFact)).all()
        assert len(facts) == 1
        assert facts[0].commission_rate == Decimal("0.300000")
        run = db.scalar(select(TermsResearchRun))
        assert run is not None
        assert run.checked_at == source_checked_at
        assert run.updated_at >= first_heartbeat


def test_fixture_attempt_audit_preserves_duplicate_run_flag() -> None:
    fixture = terms_research._load_fixture("pictory.ai")
    assert fixture is not None
    with SessionLocal() as db:
        first = terms_research._collect_fixture(db, "pictory.ai", fixture)
        second = terms_research._collect_fixture(db, "pictory.ai", fixture)
        audits = db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "terms_research_run")
            .order_by(AuditLog.id.asc())
        ).all()

    assert first["duplicate_run"] is False
    assert second["duplicate_run"] is True
    assert [audit.payload_json["duplicate_run"] for audit in audits] == [False, True]


def _reworded_official_pages(_domain: str, **_kwargs):
    return (
        [
            {
                "url": "https://merchant.example.org/affiliate-terms",
                "title": "Affiliate Program Terms",
                "text": (
                    "Affiliates are prohibited from bidding on trademark keywords. "
                    "Non-brand generic keywords are expressly allowed for paid search. "
                    "Direct linking from PPC ads is forbidden. "
                    "Partners receive a recurring commission of 30%."
                ),
                "links": [],
            }
        ],
        [],
    )


def test_reworded_permission_proposals_refresh_in_place_with_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terms_research, "discover_official_pages", _official_pages)
    first = client.post(
        "/api/programs/research",
        json={"domain": "merchant.example.org"},
    ).json()
    original_ids = {
        (item["scope"], item["decision"]): item["id"]
        for item in first["terms_evidence"]
    }
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        _reworded_official_pages,
    )

    second = client.post(
        "/api/programs/research",
        json={"domain": "merchant.example.org"},
    ).json()

    assert second["imported_terms_evidence"] == 0
    assert second["duplicate_terms_evidence"] == 4
    assert second["refreshed_terms_evidence"] == 4
    with SessionLocal() as db:
        evidence = db.scalars(select(TermsEvidence)).all()
        audits = db.scalars(
            select(AuditLog).where(AuditLog.entity_type == "terms_evidence")
        ).all()
    assert len(evidence) == 4
    assert {
        (item.scope, item.decision.value): item.id for item in evidence
    } == original_ids
    assert len(audits) == 4
    assert all(audit.payload_json["permissions_changed"] is False for audit in audits)
    attempts = client.get(
        f"/api/programs/{first['program_id']}/research-attempts"
    ).json()
    assert attempts[0]["imported_terms_evidence"] == 0
    assert attempts[0]["duplicate_terms_evidence"] == 4
    assert attempts[0]["refreshed_terms_evidence"] == 4
    assert attempts[0]["imported_commission_facts"] == 0
    assert attempts[0]["refreshed_commission_facts"] == 1
    program = client.get("/api/programs").json()[0]
    assert program["paid_search_permission"] == "NOT_CHECKED"
    assert program["brand_keyword_permission"] == "NOT_CHECKED"
    assert program["non_brand_permission"] == "NOT_CHECKED"
    assert program["direct_link_permission"] == "NOT_CHECKED"


def test_permission_refresh_never_overwrites_accepted_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terms_research, "discover_official_pages", _official_pages)
    first = client.post(
        "/api/programs/research",
        json={"domain": "merchant.example.org"},
    ).json()
    accepted_id = next(
        item["id"]
        for item in first["terms_evidence"]
        if item["scope"] == "BRAND_KEYWORD"
    )
    with SessionLocal() as db:
        accepted = db.get(TermsEvidence, accepted_id)
        assert accepted is not None
        original_excerpt = accepted.excerpt
        accepted.review_status = EvidenceReviewStatus.ACCEPTED
        db.commit()
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        _reworded_official_pages,
    )

    second = client.post(
        "/api/programs/research",
        json={"domain": "merchant.example.org"},
    ).json()

    assert second["imported_terms_evidence"] == 1
    assert second["duplicate_terms_evidence"] == 3
    assert second["refreshed_terms_evidence"] == 3
    with SessionLocal() as db:
        accepted = db.get(TermsEvidence, accepted_id)
        evidence = db.scalars(select(TermsEvidence)).all()
    assert accepted is not None
    assert accepted.review_status == EvidenceReviewStatus.ACCEPTED
    assert accepted.excerpt == original_excerpt
    assert len(evidence) == 5


def test_changed_permission_decision_creates_new_conflict_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terms_research, "discover_official_pages", _official_pages)
    first = client.post(
        "/api/programs/research",
        json={"domain": "merchant.example.org"},
    ).json()
    paid_id = next(
        item["id"]
        for item in first["terms_evidence"]
        if item["scope"] == "PAID_SEARCH"
    )
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: (
            [
                {
                    "url": "https://merchant.example.org/affiliate-terms",
                    "title": "Affiliate Program Terms",
                    "text": "Paid search and PPC advertising are prohibited.",
                    "links": [],
                }
            ],
            [],
        ),
    )

    changed = client.post(
        "/api/programs/research",
        json={"domain": "merchant.example.org"},
    ).json()

    assert changed["imported_terms_evidence"] == 1
    assert changed["refreshed_terms_evidence"] == 0
    with SessionLocal() as db:
        paid = db.get(TermsEvidence, paid_id)
        paid_items = db.scalars(
            select(TermsEvidence).where(TermsEvidence.scope == "PAID_SEARCH")
        ).all()
    assert paid is not None and paid.decision == PermissionStatus.NON_BRAND_ONLY
    assert {item.decision for item in paid_items} == {
        PermissionStatus.NON_BRAND_ONLY,
        PermissionStatus.PROHIBITED,
    }
    assert changed["gate_status"] == "WARNING_TERMS_CONFLICT"


def test_generic_commission_sources_can_resolve_to_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def conflicting_pages(_domain: str, **_kwargs):
        return (
            [
                {
                    "url": "https://merchant.example.org/affiliate",
                    "title": "Affiliate",
                    "text": "Earn a 40% one-time commission on the first payment.",
                    "links": [],
                },
                {
                    "url": "https://merchant.example.org/partners",
                    "title": "Partners",
                    "text": "Partners receive recurring commissions up to 50% for lifetime.",
                    "links": [],
                },
            ],
            [],
        )

    monkeypatch.setattr(terms_research, "discover_official_pages", conflicting_pages)
    body = client.post(
        "/api/programs/research", json={"domain": "merchant.example.org"}
    ).json()

    assert body["status"] == "CONFLICT"
    assert body["commission_state"] == "CONFLICT"
    assert len(body["commission_facts"]) == 2
    assert body["gate_status"] == "WARNING_TERMS_UNVERIFIED"


def _pictory_live_pages(_domain: str, **_kwargs):
    return (
        [
            {
                "url": "https://partners.pictory.ai/signup/40690",
                "title": "Pictory affiliate signup",
                "text": "Earn a 40% one-time commission on the first payment.",
                "links": [],
            },
            {
                "url": "https://pictory.ai/partnernow",
                "title": "Partner with Pictory",
                "text": (
                    "Annual SAVE MORE THAN 15% Affiliate Partnership. "
                    "Earn recurring commissions up to 50% for lifetime."
                ),
                "links": [],
            },
        ],
        [],
    )


def test_fixture_to_live_refresh_reuses_semantic_facts_and_keeps_ppc_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = client.post("/api/programs/research", json={"domain": "pictory.ai"}).json()
    original_ids = {
        fact["commission_rate"]: fact["id"] for fact in fixture["commission_facts"]
    }
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        _pictory_live_pages,
    )

    live = client.post("/api/programs/research", json={"domain": "pictory.ai"}).json()

    assert live["status"] == "CONFLICT"
    assert live["commission_state"] == "CONFLICT"
    assert live["imported_commission_facts"] == 0
    assert live["duplicate_commission_facts"] == 2
    assert live["refreshed_commission_facts"] == 2
    with SessionLocal() as db:
        facts = db.scalars(
            select(CommissionFact).order_by(CommissionFact.commission_rate.asc())
        ).all()
        audits = db.scalars(
            select(AuditLog).where(AuditLog.entity_type == "commission_fact")
        ).all()
    assert len(facts) == 2
    by_rate = {str(fact.commission_rate): fact for fact in facts}
    assert by_rate["0.400000"].id == original_ids["0.400000"]
    assert by_rate["0.500000"].id == original_ids["0.500000"]
    assert by_rate["0.500000"].commission_type.value == "RECURRING_LIFETIME"
    assert all(fact.collected_by == "AUTOMATED_WEB" for fact in facts)
    assert len(audits) == 2
    assert all(audit.payload_json["permissions_changed"] is False for audit in audits)
    program = client.get("/api/programs").json()[0]
    assert program["paid_search_permission"] == "NOT_CHECKED"
    assert program["brand_keyword_permission"] == "NOT_CHECKED"
    assert program["non_brand_permission"] == "NOT_CHECKED"
    assert program["direct_link_permission"] == "NOT_CHECKED"


def test_pricing_discount_near_affiliate_copy_is_not_a_commission_fact() -> None:
    specs = terms_research._extract_commission_specs(
        [
            {
                "url": "https://merchant.example.org/partners",
                "title": "Partners",
                "text": (
                    "Annual SAVE MORE THAN 15% Affiliate Partnership "
                    "Earn recurring commissions of up to 50% for lifetime."
                ),
                "links": [],
            }
        ]
    )

    assert len(specs) == 1
    assert specs[0]["commission_rate"] == Decimal("0.50")
    assert specs[0]["commission_type"] == CommissionType.RECURRING_LIFETIME
    assert specs[0]["rate_is_maximum"] is True


def test_live_refresh_never_overwrites_an_accepted_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = client.post("/api/programs/research", json={"domain": "pictory.ai"}).json()
    accepted_id = next(
        fact["id"]
        for fact in seeded["commission_facts"]
        if fact["commission_rate"] == "0.400000"
    )
    with SessionLocal() as db:
        accepted = db.get(CommissionFact, accepted_id)
        assert accepted is not None
        original_excerpt = accepted.excerpt
        accepted.review_status = EvidenceReviewStatus.ACCEPTED
        db.commit()
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: (_pictory_live_pages(_domain)[0][:1], []),
    )

    live = client.post("/api/programs/research", json={"domain": "pictory.ai"}).json()

    assert live["imported_commission_facts"] == 1
    assert live["refreshed_commission_facts"] == 0
    with SessionLocal() as db:
        accepted = db.get(CommissionFact, accepted_id)
        facts = db.scalars(select(CommissionFact)).all()
    assert accepted is not None
    assert accepted.review_status == EvidenceReviewStatus.ACCEPTED
    assert accepted.excerpt == original_excerpt
    assert len(facts) == 3


def test_no_new_source_keeps_existing_program_commission_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post("/api/programs/research", json={"domain": "pictory.ai"})
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: ([], []),
    )

    result = client.post(
        "/api/programs/research",
        json={"domain": "pictory.ai"},
    ).json()

    assert result["status"] == "MANUAL_INPUT_REQUIRED"
    assert result["commission_state"] == "CONFLICT"
    assert result["commission_facts"] == []
    assert result["refreshed_commission_facts"] == 0


def test_collector_rejects_private_and_off_domain_urls() -> None:
    with pytest.raises(ValueError, match="public"):
        terms_research._validate_public_url("https://127.0.0.1/terms", "127.0.0.1")
    with pytest.raises(ValueError, match="leaves"):
        terms_research._validate_public_url(
            "https://attacker.example/terms", "merchant.example.org"
        )
    with pytest.raises(ValueError, match="HTTPS"):
        terms_research._validate_public_url(
            "https://merchant.example.org:8443/terms", "merchant.example.org"
        )

    pages, errors = terms_research.discover_official_pages("merchant.test")
    assert pages == []
    assert errors == ["Reserved/non-public domain; automatic collection was skipped."]


def test_fetch_error_classification_retries_only_temporary_failures() -> None:
    url = "https://merchant.example.org/affiliate-terms"
    assert terms_research._fetch_error_is_retryable(URLError("timed out")) is True
    assert terms_research._fetch_error_is_retryable(
        HTTPError(url, 429, "rate limited", None, None)
    ) is True
    assert terms_research._fetch_error_is_retryable(
        HTTPError(url, 503, "unavailable", None, None)
    ) is True
    assert terms_research._fetch_error_is_retryable(
        HTTPError(url, 404, "not found", None, None)
    ) is False
    assert terms_research._fetch_error_is_retryable(ValueError("unsafe")) is False
    assert terms_research._format_fetch_error(
        url, HTTPError(url, 503, "unavailable", None, None)
    ).startswith(terms_research.RETRYABLE_ERROR_PREFIX)
    assert not terms_research._format_fetch_error(
        url, HTTPError(url, 404, "not found", None, None)
    ).startswith(terms_research.RETRYABLE_ERROR_PREFIX)


def test_discovery_prioritizes_saved_deep_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "merchant.example.org"
    deep_url = "https://merchant.example.org/legal/document/42"
    fetched: list[str] = []

    def fake_fetch(url: str, _domain: str) -> dict:
        fetched.append(url)
        if url == f"https://{domain}/":
            return {"url": url, "title": "Home", "text": "Welcome", "links": []}
        if url == deep_url:
            return {
                "url": url,
                "title": "Publisher Policy",
                "text": "Non-brand generic keywords are allowed for paid search.",
                "links": [],
            }
        raise ValueError("not found")

    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    monkeypatch.setattr(terms_research, "_fetch_page", fake_fetch)

    pages, _errors = terms_research.discover_official_pages(
        domain,
        priority_urls=[deep_url],
    )

    assert deep_url in fetched
    assert [page["url"] for page in pages] == [deep_url]


def test_collector_passes_stored_evidence_url_to_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "merchant.example.org"
    deep_url = "https://merchant.example.org/legal/document/42"
    captured: dict[str, list[str]] = {}
    with SessionLocal() as db:
        merchant = Merchant(name="Merchant", website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Merchant Affiliate Program")
        db.add(program)
        db.flush()
        db.add(
            TermsEvidence(
                program_id=program.id,
                source_url=deep_url,
                excerpt="Non-brand generic keywords are allowed for paid search.",
                evidence_hash="stored-deep-source".ljust(64, "s"),
                checked_at=datetime.now(UTC),
                reviewer="test",
                confidence=0.95,
                decision=PermissionStatus.NON_BRAND_ONLY,
                scope="PAID_SEARCH",
                applies_to="PAID_SEARCH",
                review_status=EvidenceReviewStatus.ACCEPTED,
                source_authority=SourceAuthority.OFFICIAL,
            )
        )
        db.commit()

        def saved_page(_domain: str, *, priority_urls=()):
            captured["urls"] = list(priority_urls)
            return (
                [
                    {
                        "url": deep_url,
                        "title": "Publisher Policy",
                        "text": "Non-brand generic keywords are allowed for paid search.",
                        "links": [],
                    }
                ],
                [],
            )

        monkeypatch.setattr(terms_research, "discover_official_pages", saved_page)
        result = terms_research.collect_domain_proposal(db, domain)

    assert captured["urls"] == [deep_url]
    assert result["run"].permission_proposals[0]["scope"] == "PAID_SEARCH"
