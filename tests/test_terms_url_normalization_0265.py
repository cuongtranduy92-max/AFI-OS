from __future__ import annotations

from sqlalchemy import delete

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AuditAction
from afi_os.models import AuditLog
from afi_os.services import terms_research


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_discovery_url_removes_only_known_tracking_fields() -> None:
    url = (
        "https://merchant.example.org/affiliate-terms?"
        "nav=mega&utm_Source=menu&gclid=click-1&document=42&signature=a%2Bb&ref=partner"
    )

    normalized = terms_research._normalize_discovery_url(url)

    assert normalized == (
        "https://merchant.example.org/affiliate-terms?"
        "document=42&signature=a%2Bb&ref=partner"
    )
    assert terms_research._normalize_discovery_url(normalized) == normalized


def test_discovery_fetches_tracking_variants_once_but_keeps_business_queries(
    monkeypatch,
) -> None:
    domain = "merchant.example.org"
    root_url = f"https://{domain}/"
    policy_url = f"https://{domain}/affiliate-terms"
    document_url = f"{policy_url}?document=42"
    fetched: list[str] = []

    def fake_fetch(url: str, _domain: str) -> dict:
        fetched.append(url)
        if url == root_url:
            return {
                "url": root_url,
                "title": "Merchant",
                "text": "Welcome",
                "links": [
                    f"{policy_url}?nav=mega&utm_source=menu",
                    policy_url,
                    f"{document_url}&utm_campaign=footer",
                ],
            }
        if url in {policy_url, document_url}:
            return {
                "url": url,
                "title": "Affiliate policy",
                "text": "Paid search is prohibited for affiliate partners.",
                "links": [],
            }
        raise ValueError("not found")

    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    monkeypatch.setattr(terms_research, "_fetch_page", fake_fetch)

    pages, _errors = terms_research.discover_official_pages(domain)

    assert fetched.count(policy_url) == 1
    assert fetched.count(document_url) == 1
    assert {page["url"] for page in pages} == {policy_url, document_url}


def test_old_tracking_snapshot_duplicates_do_not_create_false_source_change() -> None:
    domain = "merchant.example.org"
    policy_url = f"https://{domain}/affiliate-terms"
    press_url = f"https://{domain}/press-and-partners"
    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        db.add(
            AuditLog(
                entity_type="terms_research_run",
                entity_id="1",
                action=AuditAction.IMPORT,
                actor="official-web-v5",
                payload_json={
                    "domain": domain,
                    "source_snapshots": [
                        {
                            "url": policy_url,
                            "content_sha256": "a" * 64,
                            "text_chars": 100,
                            "relevant_chars": 80,
                        },
                        {
                            "url": f"{policy_url}?nav=mega",
                            "content_sha256": "a" * 64,
                            "text_chars": 100,
                            "relevant_chars": 80,
                        },
                        {
                            "url": f"{press_url}?utm_source=menu",
                            "content_sha256": "b" * 64,
                            "text_chars": 90,
                            "relevant_chars": 60,
                        },
                    ],
                },
            )
        )
        db.commit()

        status, changes = terms_research._compare_source_snapshots(
            db,
            domain,
            [
                {
                    "url": policy_url,
                    "content_sha256": "a" * 64,
                    "text_chars": 100,
                    "relevant_chars": 80,
                    "truncated": False,
                },
                {
                    "url": press_url,
                    "content_sha256": "b" * 64,
                    "text_chars": 90,
                    "relevant_chars": 60,
                    "truncated": False,
                },
            ],
            collection_errors=[],
        )

    assert status == "UNCHANGED"
    assert changes == []
