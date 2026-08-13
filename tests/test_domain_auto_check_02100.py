from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from afi_os.api import portfolio
from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import ResearchStatus
from afi_os.main import app
from afi_os.models import MetricSnapshot, Project
from afi_os.services.traffic_provider import (
    TrafficObservation,
    collect_project_traffic,
    fetch_semrush,
    fetch_similarweb,
)

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_ui_only_asks_for_domain_and_removes_manual_traffic_fields() -> None:
    script = (ROOT / "apps" / "web" / "app.js").read_text(encoding="utf-8")

    assert 'request("/portfolio/projects/auto-check"' in script
    assert "Không cần nhập traffic, ngày hay URL nguồn" in script
    assert 'id="projectTrafficForm"' not in script
    assert 'name="website_traffic_monthly"' not in script
    assert 'name="observed_date"' not in script
    assert 'name="source_url"' not in script


def test_missing_provider_returns_connection_required_without_inventing_traffic() -> None:
    with SessionLocal() as db:
        project = Project(domain="auto-no-provider.example", brand_name="Auto No Provider")
        db.add(project)
        db.commit()
        before = db.query(MetricSnapshot).filter_by(project_id=project.id).count()
        result = collect_project_traffic(
            db,
            project,
            readiness_getter=lambda: {
                "status": "CONNECTION_REQUIRED",
                "provider": None,
                "api_key_present": False,
                "setup_command": "SETUP-TRAFFIC-DATA.command",
            },
        )
        after = db.query(MetricSnapshot).filter_by(project_id=project.id).count()

    assert result["status"] == "CONNECTION_REQUIRED"
    assert result["requires_user"] is True
    assert result["setup_command"] == "SETUP-TRAFFIC-DATA.command"
    assert before == after == 0


def test_provider_parsers_keep_exact_domain_source_and_never_expose_api_key() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    similarweb = fetch_similarweb(
        "example.com",
        "similarweb-secret",
        now=now,
        transport=lambda url, params: httpx.Response(
            200,
            json={"visits": [{"date": "2026-07-01", "visits": 25432}]},
        ),
    )
    semrush = fetch_semrush(
        "example.com",
        "semrush-secret",
        now=now,
        transport=lambda url, params: httpx.Response(
            200,
            text="target,visits\nexample.com,18900\n",
        ),
    )

    assert similarweb.monthly_visits == Decimal("25432")
    assert "example.com" in similarweb.source_url
    assert "similarweb-secret" not in similarweb.source_url
    assert semrush.monthly_visits == Decimal("18900")
    assert "example.com" in semrush.source_url
    assert "semrush-secret" not in semrush.source_url


def test_auto_check_reports_every_unavailable_source_instead_of_blank_data(monkeypatch) -> None:
    domain = "one-box-auto-check.example"
    monkeypatch.setattr(
        portfolio,
        "collect_domain_proposal",
        lambda db, checked_domain: {
            "run": SimpleNamespace(status=ResearchStatus.MANUAL_INPUT_REQUIRED),
            "program": None,
            "source_urls": [f"https://{checked_domain}/affiliate"],
        },
    )
    monkeypatch.setattr(
        portfolio,
        "collect_project_traffic",
        lambda db, project: {
            "status": "CONNECTION_REQUIRED",
            "provider": None,
            "detail": "Kết nối traffic provider một lần.",
            "requires_user": True,
            "fields": ["website_traffic_monthly"],
            "source_urls": [],
            "setup_command": "SETUP-TRAFFIC-DATA.command",
        },
    )

    response = client.post(
        "/api/portfolio/projects/auto-check",
        json={"domain": domain, "actor": "auto-check-test"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["domain"] == domain
    assert body["permissions_changed"] is False
    assert body["google_ads_write"] is False
    assert any(item["status"] == "CONNECTION_REQUIRED" for item in body["sources"])
    assert {item["source"] for item in body["sources"]} >= {
        "Affiliate & Terms",
        "Từ khóa & CPC",
        "Affiliate account",
        "Economics",
        "Quảng cáo thị trường",
        "Hồ sơ pháp lý",
    }


def test_auto_provider_stores_source_date_confidence_and_deduplicates() -> None:
    now = datetime(2026, 8, 13, 9, 30, tzinfo=UTC)
    observation = TrafficObservation(
        provider="SIMILARWEB",
        monthly_visits=Decimal("25001"),
        period=now.date().replace(day=1),
        source_url="https://api.similarweb.com/v1/website/auto-store.example/visits",
    )
    with SessionLocal() as db:
        project = Project(domain="auto-store.example", brand_name="Auto Store")
        db.add(project)
        db.commit()
        fetchers = {"SIMILARWEB": lambda domain, key, now: observation}

        def readiness() -> dict:
            return {
                "status": "READY",
                "provider": "SIMILARWEB",
                "api_key_present": True,
                "setup_command": "SETUP-TRAFFIC-DATA.command",
            }

        first = collect_project_traffic(
            db,
            project,
            now=now,
            readiness_getter=readiness,
            credential_reader=lambda label: "never-store-this-secret",
            fetchers=fetchers,
        )
        second = collect_project_traffic(
            db,
            project,
            now=now,
            readiness_getter=readiness,
            credential_reader=lambda label: "never-store-this-secret",
            fetchers=fetchers,
        )
        snapshot = db.get(MetricSnapshot, first["snapshot_id"])

        assert first["created"] is True
        assert second["created"] is False
        assert snapshot is not None
        assert snapshot.observed_at == now.replace(tzinfo=None)
        assert snapshot.source_url == observation.source_url
        assert snapshot.confidence == 0.8
        assert "never-store-this-secret" not in str(snapshot.payload_json)
