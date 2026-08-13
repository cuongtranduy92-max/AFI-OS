from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    CommissionType,
    EvidenceReviewStatus,
    PermissionStatus,
    ResearchStatus,
    SourceAuthority,
)
from afi_os.models import AuditLog, CommissionFact, Merchant, Program, TermsResearchRun
from afi_os.services import terms_research


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program(domain: str, signup_url: str) -> int:
    with SessionLocal() as db:
        merchant = Merchant(name=domain, website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(
            merchant_id=merchant.id,
            name=f"{domain} Affiliate",
            signup_url=signup_url,
        )
        db.add(program)
        db.commit()
        return program.id


def _page(url: str, text: str, authority: SourceAuthority) -> dict:
    return {
        "url": url,
        "title": "Affiliate signup",
        "text": text,
        "links": ["https://unrelated.example.net/do-not-crawl"],
        "source_authority": authority.value,
    }


def test_saved_external_signup_is_partner_portal_proposal_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "merchant.example.org"
    signup_url = "https://portal.example.net/signup/merchant"
    program_id = _program(domain, signup_url)
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: ([], []),
    )
    monkeypatch.setattr(
        terms_research,
        "discover_partner_portal_signup",
        lambda url: (
            [
                _page(
                    url,
                    "Paid search is prohibited. Partners earn a recurring "
                    "commission of 30% for lifetime.",
                    SourceAuthority.PARTNER_PORTAL,
                )
            ],
            [],
        ),
    )

    with SessionLocal() as db:
        result = terms_research.collect_domain_proposal(db, domain)
        program = db.get(Program, program_id)
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.entity_type == "terms_research_run")
            .order_by(AuditLog.id.desc())
        )

    assert result["run"].status == ResearchStatus.PROPOSAL_READY
    assert result["gate_status"] == "WARNING_TERMS_UNVERIFIED"
    assert len(result["evidence"]) == 1
    assert result["evidence"][0].source_authority == SourceAuthority.PARTNER_PORTAL
    assert result["evidence"][0].review_status == EvidenceReviewStatus.PROPOSED
    assert len(result["facts"]) == 1
    assert result["facts"][0].source_authority == SourceAuthority.PARTNER_PORTAL
    assert result["facts"][0].commission_type == CommissionType.RECURRING_LIFETIME
    assert result["source_authorities"] == {
        signup_url: SourceAuthority.PARTNER_PORTAL.value
    }
    assert result["run"].permission_proposals[0]["source_authority"] == "PARTNER_PORTAL"
    assert audit is not None
    assert audit.payload_json["source_authorities"] == result["source_authorities"]
    assert program is not None
    assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
    assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
    assert program.non_brand_permission == PermissionStatus.NOT_CHECKED
    assert program.direct_link_permission == PermissionStatus.NOT_CHECKED


def test_official_and_partner_portal_commission_disagreement_is_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "conflict.example.org"
    signup_url = "https://affiliate-platform.example.net/signup/conflict"
    _program(domain, signup_url)
    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: (
            [
                _page(
                    f"https://{domain}/affiliate",
                    "Earn a 40% one-time commission on the first payment.",
                    SourceAuthority.OFFICIAL,
                )
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        terms_research,
        "discover_partner_portal_signup",
        lambda url: (
            [
                _page(
                    url,
                    "Receive recurring commissions up to 50% for lifetime.",
                    SourceAuthority.PARTNER_PORTAL,
                )
            ],
            [],
        ),
    )

    with SessionLocal() as db:
        result = terms_research.collect_domain_proposal(db, domain)

    assert result["run"].status == ResearchStatus.CONFLICT
    assert result["commission_state"] == "CONFLICT"
    assert {fact.source_authority for fact in result["facts"]} == {
        SourceAuthority.OFFICIAL,
        SourceAuthority.PARTNER_PORTAL,
    }
    assert result["program"].paid_search_permission == PermissionStatus.NOT_CHECKED


def test_legacy_snapshots_recover_official_authority_without_overstating_unknowns() -> None:
    official_url = "https://merchant.example.org/affiliate"
    portal_url = "https://portal.example.net/signup/merchant"

    recovered = terms_research.source_authorities_from_audit_payload(
        {
            "source_snapshots": [
                {"url": official_url, "content_sha256": "a" * 64},
                {
                    "url": portal_url,
                    "content_sha256": "b" * 64,
                    "source_authority": "PARTNER_PORTAL",
                },
                {
                    "url": "https://invalid.example/source",
                    "source_authority": "NOT_A_REAL_AUTHORITY",
                },
            ]
        }
    )

    assert recovered == {
        official_url: SourceAuthority.OFFICIAL.value,
        portal_url: SourceAuthority.PARTNER_PORTAL.value,
    }


def test_partner_portal_fetches_only_exact_saved_public_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)

    def fake_fetch(url: str, domain: str) -> dict:
        captured.append((url, domain))
        return {
            "url": url,
            "title": "Signup",
            "text": "Affiliate recurring commission of 20% for lifetime.",
            "links": ["https://another.example.net/terms"],
            "truncated": False,
        }

    monkeypatch.setattr(terms_research, "_fetch_page", fake_fetch)
    pages, errors = terms_research.discover_partner_portal_signup(
        "https://portal.example.net/signup/abc?utm_source=mail&ref=123"
    )

    assert errors == []
    assert captured == [
        ("https://portal.example.net/signup/abc?ref=123", "portal.example.net")
    ]
    assert len(pages) == 1
    assert pages[0]["source_authority"] == SourceAuthority.PARTNER_PORTAL.value
    assert pages[0]["links"] == ["https://another.example.net/terms"]


def test_partner_portal_rejects_credentialed_signup_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    pages, errors = terms_research.discover_partner_portal_signup(
        "https://user:secret@portal.example.net/signup"
    )

    assert pages == []
    assert len(errors) == 1
    assert "credential-free HTTPS" in errors[0]


def test_external_history_never_enters_merchant_domain_discovery() -> None:
    domain = "memory.example.org"
    official_url = f"https://{domain}/affiliate/terms"
    external_url = "https://portal.example.net/signup/memory"
    program_id = _program(domain, external_url)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                program_id=program_id,
                domain=domain,
                fixture_version="partner-portal-memory-test",
                status=ResearchStatus.MANUAL_INPUT_REQUIRED,
                checked_at=now,
                discovery_confidence=0.0,
                source_urls=[external_url, official_url],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash="partner-portal-source-memory".ljust(64, "p"),
            )
        )
        db.commit()
        program = db.get(Program, program_id)
        remembered = terms_research._stored_source_urls(db, program)

    assert remembered == [official_url]


def test_authority_is_part_of_automated_deduplication() -> None:
    domain = "authority.example.org"
    source_url = f"https://{domain}/affiliate"
    program_id = _program(domain, source_url)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            CommissionFact(
                program_id=program_id,
                scope="COMMISSION",
                source_url=source_url,
                source_authority=SourceAuthority.PARTNER_PORTAL,
                excerpt="Recurring commission of 25%.",
                checked_at=now,
                confidence=0.8,
                commission_type=CommissionType.RECURRING_UNSPECIFIED,
                commission_rate=Decimal("0.25"),
                applies_to="RECURRING_UNSPECIFIED",
                review_status=EvidenceReviewStatus.PROPOSED,
                collected_by="AUTOMATED_WEB",
                evidence_hash="partner-authority-existing".ljust(64, "a"),
            )
        )
        db.commit()
        program = db.get(Program, program_id)
        assert program is not None
        facts, imported, duplicates, refreshed = terms_research._import_commission_specs(
            db,
            program,
            [
                {
                    "source_url": source_url,
                    "source_authority": SourceAuthority.OFFICIAL,
                    "excerpt": "Recurring commission of 25%.",
                    "confidence": 0.8,
                    "commission_type": CommissionType.RECURRING_UNSPECIFIED,
                    "commission_rate": Decimal("0.25"),
                    "rate_is_maximum": False,
                    "applies_to": "RECURRING_UNSPECIFIED",
                }
            ],
            now,
        )

    assert imported == 1
    assert duplicates == 0
    assert refreshed == 0
    assert facts[0].source_authority == SourceAuthority.OFFICIAL
