from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from afi_os.db import Base, engine
from afi_os.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _intake(domain: str) -> dict:
    response = client.post(
        "/api/portfolio/projects/intake",
        json={"domain": domain, "actor": "network-test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project"]


def _snapshot(domain: str, source_slug: str, advertisers: list[dict]) -> None:
    response = client.post(
        "/api/ad-intelligence/advertiser-snapshots",
        json={
            "project_domain": domain,
            "source_url": f"https://source.example/{source_slug}",
            "source_name": "Sourced network fixture",
            "checked_at": "2026-08-12T20:00:00Z",
            "evidence_excerpt": f"Visible advertiser result for {domain}.",
            "result_set_complete": True,
            "confidence": 0.9,
            "actor": "network-test",
            "advertisers": advertisers,
        },
    )
    assert response.status_code == 200, response.text


def test_project_network_auto_expands_advertisers_and_their_other_projects() -> None:
    center = _intake("alpha.example")
    other = _intake("beta.example")
    _snapshot(
        "alpha.example",
        "alpha",
        [
            {
                "external_key": "AR-SHARED",
                "advertiser_name": "Shared Advertiser",
                "reported_ad_count": 72,
            },
            {
                "external_key": "AR-ALPHA",
                "advertiser_name": "Alpha Only",
                "reported_ad_count": 3,
            },
        ],
    )
    _snapshot(
        "beta.example",
        "beta",
        [
            {
                "external_key": "AR-SHARED",
                "advertiser_name": "Shared Advertiser",
                "reported_ad_count": 5,
            }
        ],
    )

    response = client.get(f"/api/ad-intelligence/projects/{center['id']}/network")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["collection_state"] == "AVAILABLE"
    assert body["domain"] == "alpha.example"
    assert len(body["advertisers"]) == 2

    shared = next(
        item for item in body["advertisers"] if item["advertiser_name"] == "Shared Advertiser"
    )
    assert shared["reported_ads"] == 72
    assert shared["related_project_count"] == 2
    assert {project["project_id"] for project in shared["projects"]} == {
        center["id"],
        other["id"],
    }
    assert {project["domain"] for project in shared["projects"]} == {
        "alpha.example",
        "beta.example",
    }
    assert all(project["source_count"] == 1 for project in shared["projects"])
    assert shared["observed_at"].startswith("2026-08-12T20:00:00")
    assert all(project["observed_at"] for project in shared["projects"])


def test_uncollected_project_is_unknown_not_zero() -> None:
    project = _intake("unknown.example")
    response = client.get(f"/api/ad-intelligence/projects/{project['id']}/network")
    assert response.status_code == 200
    assert response.json()["collection_state"] == "NOT_COLLECTED"
    assert response.json()["advertisers"] == []


def test_missing_network_entities_return_404() -> None:
    assert client.get("/api/ad-intelligence/projects/999999/network").status_code == 404
    assert client.get("/api/ad-intelligence/advertisers/999999/projects").status_code == 404


def test_ui_starts_with_find_and_auto_expands_network() -> None:
    page = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "apps" / "web" / "app.js").read_text(encoding="utf-8")

    portfolio_nav = page.index('class="nav-item active" data-view="portfolio"')
    command_nav = page.index('data-view="command"')
    assert portfolio_nav < command_nav
    assert '<section id="view-portfolio" class="view active">' in page
    assert "Mạng lưới tự mở rộng" in script
    assert 'request(`/ad-intelligence/projects/${projectId}/network`)' in script
    assert 'data-project-network="${project.project_id}"' in script
    assert "Đây không phải là 0 nhà quảng cáo" in script
