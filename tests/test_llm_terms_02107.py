from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from afi_os.db import Base
from afi_os.enums import EvidenceReviewStatus, PermissionStatus
from afi_os.models import (
    CommercialProposal,
    LLMExtractionRun,
    Merchant,
    Program,
    Project,
)
from afi_os.services.commercial_review import review_commercial_proposal
from afi_os.services.llm_keychain import KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE, store_credential
from afi_os.services.llm_terms import (
    ANTHROPIC_MESSAGES_URL,
    ANTHROPIC_VERSION,
    call_anthropic,
    extract_terms_from_pages,
)
from afi_os.services.project_check import build_project_step_one

SOURCE_URL = "https://llm-terms.example/affiliate-terms"
SOURCE = (
    "Partners earn 30% recurring commissions for the lifetime of each customer. "
    "The Pro package costs $100 per month. "
    "Payouts are sent via PayPal after 30 days with a minimum payout of $50 and a "
    "60-day cookie. Paid search ads are not allowed in the affiliate program."
)


def _response() -> str:
    return json.dumps(
        {
            "commission": {
                "type": "RECURRING_LIFETIME",
                "percent": 30,
                "rate_is_upper_bound": False,
                "recurring_months": None,
                "flat_usd": None,
                "quote": (
                    "Partners earn 30% recurring commissions for the lifetime of each "
                    "customer."
                ),
            },
            "packages": [
                {
                    "name": "Pro",
                    "price_usd": 100,
                    "period": "month",
                    "quote": "The Pro package costs $100 per month.",
                }
            ],
            "payment": {
                "gateways": ["PayPal"],
                "min_payment_usd": 50,
                "clear_days": 30,
                "cookie_days": 60,
                "net_platform": None,
                "quote": (
                    "Payouts are sent via PayPal after 30 days with a minimum payout of $50 "
                    "and a 60-day cookie."
                ),
            },
            "terms": {
                "ads_allowed": False,
                "brand_bid_restricted": None,
                "quote": "Paid search ads are not allowed in the affiliate program.",
            },
            "confidence": 0.95,
        }
    )


def _database(tmp_path: Path) -> tuple[Session, Project]:
    engine = create_engine(f"sqlite:///{tmp_path / 'llm.db'}")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    merchant = Merchant(name="LLM Terms", website_domain="llm-terms.example", country="US")
    program = Program(merchant=merchant, name="LLM Terms Affiliate")
    project = Project(domain="llm-terms.example", brand_name="LLM Terms", program=program)
    db.add(project)
    db.commit()
    return db, project


def test_extract_cache_and_human_review_gate(tmp_path: Path) -> None:
    db, project = _database(tmp_path)
    calls = {"credential": 0, "sender": 0}

    def credential() -> str:
        calls["credential"] += 1
        return "test-secret-never-persist"

    def sender(_system: str, _user: str, _key: str, _model: str) -> str:
        calls["sender"] += 1
        return _response()

    pages = [{"url": SOURCE_URL, "text": SOURCE}]
    first = extract_terms_from_pages(
        db,
        project,
        pages,
        credential_reader=credential,
        sender=sender,
    )
    second = extract_terms_from_pages(
        db,
        project,
        pages,
        credential_reader=lambda: (_ for _ in ()).throw(AssertionError("cache read key")),
        sender=lambda *_args: (_ for _ in ()).throw(AssertionError("cache called Claude")),
    )

    assert first["cached"] is False
    assert second["cached"] is True
    assert calls == {"credential": 1, "sender": 1}
    assert db.scalar(select(LLMExtractionRun)) is not None
    assert all(
        item.review_status == EvidenceReviewStatus.PROPOSED
        for item in first["commission_facts"]
    )
    assert all(
        item.review_status == EvidenceReviewStatus.PROPOSED
        for item in first["terms_evidence"]
    )
    assert project.program.paid_search_permission == PermissionStatus.NOT_CHECKED
    db.expire_all()
    project = db.get(Project, project.id)
    assert project is not None
    before = build_project_step_one(project)
    assert before.fields["accepted_commission_rate"].value is None
    assert before.fields["average_package_price"].value is None

    commission = first["commission_facts"][0]
    commission.review_status = EvidenceReviewStatus.ACCEPTED
    db.commit()
    for proposal in db.scalars(select(CommercialProposal)).all():
        review_commercial_proposal(
            db,
            project,
            proposal,
            action="ACCEPT",
            reviewed_by="test-operator",
        )

    db.expire_all()
    project = db.get(Project, project.id)
    assert project is not None
    accepted = build_project_step_one(project)
    assert accepted.fields["accepted_commission_rate"].value == 30.0
    assert accepted.fields["average_package_price"].value == 100.0
    assert accepted.fields["payout_methods"].value == '["PayPal"]'
    assert accepted.fields["cookie_days"].value == 60.0
    assert project.program.paid_search_permission == PermissionStatus.NOT_CHECKED
    db.close()


def test_keychain_store_does_not_put_secret_in_process_arguments() -> None:
    captured = {}

    class Result:
        returncode = 0

    def runner(arguments, **kwargs):  # type: ignore[no-untyped-def]
        captured["arguments"] = arguments
        captured["input"] = kwargs["input"]
        return Result()

    secret = "sk-ant-test-never-log"
    store_credential(secret, runner=runner)

    assert KEYCHAIN_SERVICE in captured["arguments"]
    assert KEYCHAIN_ACCOUNT in captured["arguments"]
    assert secret not in captured["arguments"]
    assert secret in captured["input"]


def test_anthropic_http_contract_uses_ticket_configuration() -> None:
    captured = {}

    def post(url, **kwargs):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"content": [{"type": "text", "text": '{"ok": true}'}]},
        )

    secret = "sk-ant-contract-test"
    text = call_anthropic("system", "user", secret, "claude-haiku-4-5", post=post)

    assert text == '{"ok": true}'
    assert captured["url"] == ANTHROPIC_MESSAGES_URL
    assert captured["headers"] == {
        "x-api-key": secret,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    assert captured["json"] == {
        "model": "claude-haiku-4-5",
        "max_tokens": 2000,
        "temperature": 0,
        "system": "system",
        "messages": [{"role": "user", "content": "user"}],
    }
    assert captured["timeout"] == 60


def test_extract_terms_endpoint_runs_crawl_to_proposal_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from afi_os.api import term_extraction as api

    db, project = _database(tmp_path)
    pages = [{"url": SOURCE_URL, "text": SOURCE}]
    monkeypatch.setattr(
        api,
        "collect_domain_proposal",
        lambda _db, _domain: {"pages": pages, "program": project.program},
    )

    def fake_extract(_db, loaded_project, loaded_pages):  # type: ignore[no-untyped-def]
        return extract_terms_from_pages(
            _db,
            loaded_project,
            loaded_pages,
            credential_reader=lambda: "endpoint-test-secret",
            sender=lambda *_args: _response(),
        )

    monkeypatch.setattr(api, "extract_terms_from_pages", fake_extract)
    response = api.extract_project_terms(project.id, db)

    assert response.status == "PROPOSAL_READY"
    assert response.commission_facts[0].review_status == EvidenceReviewStatus.PROPOSED
    assert response.terms_evidence[0].review_status == EvidenceReviewStatus.PROPOSED
    assert response.commercial_proposals[0].review_status == EvidenceReviewStatus.PROPOSED
    assert response.permissions_changed is False
    assert response.campaign_state_changed is False
    assert response.google_ads_write is False
    db.close()
