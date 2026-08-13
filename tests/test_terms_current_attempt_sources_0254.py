from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from afi_os.api import programs as programs_api
from afi_os.db import Base, SessionLocal, engine
from afi_os.main import app
from afi_os.models import Merchant, Program, TermsResearchRun
from afi_os.services import terms_research

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
    return {"url": url, "title": "Affiliate", "text": text, "links": []}


def test_duplicate_run_result_keeps_sources_from_current_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "attempt-sources.example.org"
    program_id = _program(domain)
    commission_url = f"https://{domain}/affiliate-program"
    additional_url = f"https://{domain}/partner-policy"
    commission_page = _page(
        commission_url,
        "Earn a 25% lifetime recurring commission as an affiliate partner.",
    )

    with SessionLocal() as db:
        first = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: ([commission_page], []),
        )
    with SessionLocal() as db:
        second = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [
                    commission_page,
                    _page(additional_url, "Affiliate partners should read this policy."),
                ],
                [],
            ),
        )

    assert second["duplicate_run"] is True
    assert second["run"].id == first["run"].id
    assert second["run"].source_urls == [commission_url]
    assert second["source_urls"] == [commission_url, additional_url]

    run_id = second["run"].id

    def current_attempt_result(db, _domain: str) -> dict:
        run = db.get(TermsResearchRun, run_id)
        program = db.get(Program, program_id)
        assert run is not None and program is not None
        return {
            "run": run,
            "program": program,
            "facts": [],
            "evidence": [],
            "imported": 0,
            "duplicates": 1,
            "refreshed": 1,
            "commission_state": "PROPOSED",
            "imported_evidence": 0,
            "duplicate_evidence": 0,
            "refreshed_evidence": 0,
            "duplicate_run": True,
            "collection_errors": [],
            "source_urls": [commission_url, additional_url],
            "source_change_status": "CHANGED",
            "source_changes": [{"url": additional_url, "change_type": "ADDED"}],
        }

    monkeypatch.setattr(programs_api, "collect_domain_proposal", current_attempt_result)
    response = client.post("/api/programs/research", json={"domain": domain})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate_run"] is True
    assert body["source_urls"] == [commission_url, additional_url]
    assert body["source_change_status"] == "CHANGED"


def test_manual_result_exposes_current_checked_sources() -> None:
    domain = "manual-attempt-sources.example.org"
    _program(domain)
    source_url = f"https://{domain}/affiliate-policy"
    with SessionLocal() as db:
        result = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [_page(source_url, "Affiliate partner policy overview.")],
                [],
            ),
        )

    assert result["source_urls"] == [source_url]
