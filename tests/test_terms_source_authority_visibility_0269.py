from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from afi_os.db import Base, engine
from afi_os.enums import SourceAuthority
from afi_os.main import app
from afi_os.services import terms_research

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_research_response_and_history_label_official_and_partner_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = "visibility.example.org"
    official_url = f"https://{domain}/affiliate"
    portal_url = "https://network.example.net/signup/visibility"
    created = client.post(
        "/api/programs",
        json={
            "merchant_name": "Visibility",
            "website_domain": domain,
            "program_name": "Visibility Affiliate",
            "signup_url": portal_url,
        },
    )
    assert created.status_code == 200, created.text
    program_id = created.json()["id"]

    monkeypatch.setattr(
        terms_research,
        "discover_official_pages",
        lambda _domain, **_kwargs: (
            [
                {
                    "url": official_url,
                    "title": "Affiliate terms",
                    "text": "Paid search is prohibited.",
                    "links": [],
                }
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        terms_research,
        "discover_partner_portal_signup",
        lambda url: (
            [
                {
                    "url": url,
                    "title": "Partner signup",
                    "text": "Partners earn a recurring commission of 30% for lifetime.",
                    "links": [],
                    "source_authority": SourceAuthority.PARTNER_PORTAL.value,
                }
            ],
            [],
        ),
    )

    response = client.post("/api/programs/research", json={"domain": domain})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_authorities"] == {
        official_url: "OFFICIAL",
        portal_url: "PARTNER_PORTAL",
    }
    assert body["permission_proposals"] == [
        {
            "scope": "PAID_SEARCH",
            "decision": "PROHIBITED",
            "confidence": 0.9,
            "reason": "Trang chính thức có câu cấm paid search/PPC.",
            "source_authority": "OFFICIAL",
        }
    ]
    assert body["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    attempts = client.get(f"/api/programs/{program_id}/research-attempts")
    assert attempts.status_code == 200, attempts.text
    assert attempts.json()[0]["source_authorities"] == body["source_authorities"]

    program = next(
        item for item in client.get("/api/programs").json() if item["id"] == program_id
    )
    assert program["paid_search_permission"] == "NOT_CHECKED"
    assert program["brand_keyword_permission"] == "NOT_CHECKED"
    assert program["non_brand_permission"] == "NOT_CHECKED"
    assert program["direct_link_permission"] == "NOT_CHECKED"
