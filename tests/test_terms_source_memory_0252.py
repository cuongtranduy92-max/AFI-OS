from __future__ import annotations

from datetime import UTC, datetime

import pytest

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    EvidenceReviewStatus,
    PermissionStatus,
    ResearchStatus,
    SourceAuthority,
)
from afi_os.models import Merchant, Program, TermsEvidence, TermsResearchRun
from afi_os.services import terms_research


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program(domain: str, *, signup_url: str | None = None) -> int:
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


def _page(url: str, text: str) -> dict:
    return {"url": url, "title": "Affiliate policy", "text": text, "links": []}


def test_no_evidence_page_is_remembered_and_prioritized_on_next_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "memory.example.org"
    program_id = _program(domain)
    source_url = f"https://{domain}/legal/publisher-rules"
    page = _page(
        source_url,
        "Affiliate partners should read this policy before publishing links.",
    )

    with SessionLocal() as db:
        first = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: ([page], []),
        )

    assert first["run"].status == ResearchStatus.MANUAL_INPUT_REQUIRED
    assert first["run"].source_urls == [source_url]
    captured_priority: list[str] = []

    def discover(_domain: str, *, priority_urls=()):
        captured_priority.extend(priority_urls)
        return [page], []

    monkeypatch.setattr(terms_research, "discover_official_pages", discover)
    with SessionLocal() as db:
        second = terms_research.collect_domain_proposal(db, domain)
        program = db.get(Program, program_id)
        assert program is not None
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
        assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
        assert program.non_brand_permission == PermissionStatus.NOT_CHECKED
        assert program.direct_link_permission == PermissionStatus.NOT_CHECKED

    assert captured_priority == [source_url]
    assert second["duplicate_run"] is True


def test_domain_history_survives_research_before_program_creation() -> None:
    domain = "before-program.example.org"
    source_url = f"https://{domain}/partner/policy"
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                program_id=None,
                domain=domain,
                fixture_version="source-memory-test",
                status=ResearchStatus.MANUAL_INPUT_REQUIRED,
                checked_at=now,
                discovery_confidence=0.0,
                source_urls=[source_url],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash="pre-program-source-memory".ljust(64, "m"),
            )
        )
        merchant = Merchant(name="Before Program", website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Before Program Affiliate")
        db.add(program)
        db.commit()
        db.refresh(program)

        remembered = terms_research._stored_source_urls(db, program)

    assert remembered == [source_url]


def test_rejected_only_source_does_not_return_through_research_history() -> None:
    domain = "rejected-source.example.org"
    rejected_url = f"https://{domain}/affiliate/old-policy"
    kept_url = f"https://{domain}/affiliate/current-policy"
    program_id = _program(domain)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            TermsEvidence(
                program_id=program_id,
                source_url=rejected_url,
                excerpt="Rejected source claim.",
                evidence_hash="rejected-source-memory".ljust(64, "r"),
                checked_at=now,
                reviewer="operator",
                confidence=0.9,
                decision=PermissionStatus.PROHIBITED,
                scope="PAID_SEARCH",
                applies_to="PAID_SEARCH",
                review_status=EvidenceReviewStatus.REJECTED,
                source_authority=SourceAuthority.OFFICIAL,
            )
        )
        db.add(
            TermsResearchRun(
                program_id=program_id,
                domain=domain,
                fixture_version="source-memory-test",
                status=ResearchStatus.MANUAL_INPUT_REQUIRED,
                checked_at=now,
                discovery_confidence=0.0,
                source_urls=[rejected_url, kept_url],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash="rejected-history-source-memory".ljust(64, "h"),
            )
        )
        db.commit()
        program = db.get(Program, program_id)
        assert program is not None

        remembered = terms_research._stored_source_urls(db, program)

    assert remembered == [kept_url]


def test_checked_pages_are_audited_but_signup_uses_evidence_source() -> None:
    domain = "complete-sources.example.org"
    root_url = f"https://{domain}/"
    commission_url = f"https://{domain}/legal/partner-rewards"
    pages = [
        _page(root_url, "Affiliate program overview for partners."),
        _page(commission_url, "Earn a 25% recurring commission for lifetime."),
    ]

    with SessionLocal() as db:
        result = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (pages, []),
        )
        program = result["program"]
        assert program is not None
        assert program.signup_url == commission_url
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED

    assert result["run"].source_urls == sorted([root_url, commission_url])
    assert len(result["facts"]) == 1
    assert result["evidence"] == []


def test_existing_program_with_blank_signup_uses_discovered_evidence_source() -> None:
    domain = "existing-blank.example.org"
    program_id = _program(domain)
    source_url = f"https://{domain}/affiliate-program"

    with SessionLocal() as db:
        result = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [_page(source_url, "Earn a 30% recurring commission for lifetime.")],
                [],
            ),
        )
        program = db.get(Program, program_id)
        assert program is not None
        assert program.signup_url == source_url
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED

    assert result["signup_url_discovered"] is True
    assert result["commission_state"] == "PROPOSED"


def test_existing_signup_is_never_overwritten_by_new_discovery() -> None:
    domain = "preserve-signup.example.org"
    saved_signup_url = "https://partner.example.net/exact/signup/123"
    program_id = _program(domain, signup_url=saved_signup_url)
    discovered_url = f"https://{domain}/affiliate-program"

    with SessionLocal() as db:
        result = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [_page(discovered_url, "Earn a 20% recurring commission for lifetime.")],
                [],
            ),
        )
        program = db.get(Program, program_id)
        assert program is not None
        assert program.signup_url == saved_signup_url
        assert program.direct_link_permission == PermissionStatus.NOT_CHECKED

    assert result["signup_url_discovered"] is False
