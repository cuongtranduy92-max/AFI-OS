from __future__ import annotations

import csv
import io
import json
import zipfile
from email.message import Message

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.main import app
from afi_os.models import AuditLog, Merchant, Program, TermsEvidence
from afi_os.services import terms_research

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class _LargeResponse:
    def __init__(self, url: str, payload: bytes) -> None:
        self._url = url
        self._payload = payload
        self.read_sizes: list[int] = []
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return self._payload[:size]


class _LargePageOpener:
    def __init__(self, response: _LargeResponse) -> None:
        self.response = response

    def open(self, _request, timeout: int):
        assert timeout == terms_research.FETCH_TIMEOUT_SECONDS
        return self.response


def test_large_page_keeps_bounded_prefix_and_marks_truncation(monkeypatch) -> None:
    domain = "merchant.example.org"
    url = f"https://{domain}/"
    prefix = (
        b'<html><head><title>Merchant</title></head><body>'
        b'<a href="/affiliate-terms">Affiliate terms</a>'
        b'<p>Paid search is prohibited for affiliates.</p>'
    )
    payload = prefix + b"x" * (terms_research.MAX_PAGE_BYTES + 100)
    response = _LargeResponse(url, payload)

    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    monkeypatch.setattr(
        terms_research,
        "build_opener",
        lambda *_handlers: _LargePageOpener(response),
    )

    page = terms_research._fetch_page(url, domain)

    assert response.read_sizes == [terms_research.MAX_PAGE_BYTES + 1]
    assert page["truncated"] is True
    assert page["url"] == url
    assert page["links"] == [f"https://{domain}/affiliate-terms"]
    assert "Paid search is prohibited" in page["text"]
    assert len(page["text"].encode()) <= terms_research.MAX_PAGE_BYTES
    assert terms_research._extract_permission_specs([page])[0]["decision"].value == (
        "PROHIBITED"
    )
    snapshot = terms_research._source_snapshots([page])[0]
    assert snapshot["truncated"] is True
    assert len(snapshot["content_sha256"]) == 64


def test_truncated_source_marker_reaches_audit_and_evidence_pack() -> None:
    domain = "large-source.example.org"
    url = f"https://{domain}/"
    with SessionLocal() as db:
        merchant = Merchant(name="Large Source", website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Large Source Affiliate")
        db.add(program)
        db.commit()
        program_id = program.id

        result = terms_research.collect_domain_proposal(
            db,
            domain,
            fetcher=lambda _domain: (
                [
                    {
                        "url": url,
                        "title": "Affiliate policy",
                        "text": "Affiliate partners should read the publisher policy.",
                        "links": [],
                        "truncated": True,
                    }
                ],
                [],
            ),
        )
        assert result["run"].status.value == "MANUAL_INPUT_REQUIRED"
        before_audits = db.scalar(select(func.count()).select_from(AuditLog))
        before_evidence = db.scalar(select(func.count()).select_from(TermsEvidence))

    response = client.get(f"/api/programs/{program_id}/evidence-pack")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        summary = json.loads(archive.read("program-summary.json"))
        attempts = list(
            csv.DictReader(
                io.StringIO(
                    archive.read("research-attempts.csv").decode("utf-8-sig")
                )
            )
        )

    assert summary["pack_format_version"] == 4
    assert summary["collection"] == {
        "large_pages_are_bounded_to_bytes": terms_research.MAX_PAGE_BYTES,
        "latest_source_page_count": 1,
        "latest_source_authorities": {url: "OFFICIAL"},
        "latest_truncated_source_urls": [url],
    }
    assert attempts[-1]["source_page_count"] == "1"
    assert json.loads(attempts[-1]["truncated_source_urls"]) == [url]

    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        assert {
            program.paid_search_permission.value,
            program.brand_keyword_permission.value,
            program.non_brand_permission.value,
            program.direct_link_permission.value,
        } == {"NOT_CHECKED"}
        assert db.scalar(select(func.count()).select_from(AuditLog)) == before_audits
        assert db.scalar(select(func.count()).select_from(TermsEvidence)) == before_evidence
