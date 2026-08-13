from __future__ import annotations

from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import PermissionStatus
from afi_os.models import Program, TermsEvidence
from afi_os.services.operations import operations_inbox
from afi_os.services.programs import program_gate_status
from afi_os.services.terms_research import collect_domain_proposal


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _page(domain: str, text: str) -> dict:
    return {
        "url": f"https://{domain}/",
        "title": "Affiliate policy",
        "text": text,
        "links": [],
        "truncated": True,
    }


def test_truncated_hash_churn_is_partial_without_source_change_warning() -> None:
    domain = "dynamic-home.example.org"
    with SessionLocal() as db:
        first = collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [
                    _page(
                        domain,
                        "Paid search is prohibited for affiliates. Affiliate banner A.",
                    )
                ],
                [],
            ),
        )
        second = collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [
                    _page(
                        domain,
                        "Paid search is prohibited for affiliates. Affiliate banner B.",
                    )
                ],
                [],
            ),
        )
        inbox = operations_inbox(db)

    assert first["source_change_status"] == "INITIAL"
    assert second["source_change_status"] == "PARTIAL"
    assert second["source_changes"] == []
    assert not any(item["item_type"] == "TERMS_SOURCE_CHANGED" for item in inbox["items"])


def test_truncated_page_still_creates_semantic_conflict_proposals() -> None:
    domain = "truncated-policy.example.org"
    with SessionLocal() as db:
        collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [_page(domain, "Paid search is prohibited for affiliates.")],
                [],
            ),
        )
        changed = collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [
                    _page(
                        domain,
                        "Non-brand generic keywords are allowed for paid search.",
                    )
                ],
                [],
            ),
        )
        program = db.scalar(select(Program))
        assert program is not None
        evidence = list(
            db.scalars(
                select(TermsEvidence).where(TermsEvidence.program_id == program.id)
            ).all()
        )
        gate = program_gate_status(program, evidence)

    paid_search_decisions = {
        item.decision for item in evidence if item.scope == "PAID_SEARCH"
    }
    assert changed["source_change_status"] == "PARTIAL"
    assert changed["source_changes"] == []
    assert paid_search_decisions == {
        PermissionStatus.PROHIBITED,
        PermissionStatus.NON_BRAND_ONLY,
    }
    assert gate == "WARNING_TERMS_CONFLICT"
    assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
    assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
    assert program.non_brand_permission == PermissionStatus.NOT_CHECKED
    assert program.direct_link_permission == PermissionStatus.NOT_CHECKED
