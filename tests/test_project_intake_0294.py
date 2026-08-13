from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import ProjectStage, RegistrationStatus, WatchStatus
from afi_os.main import app
from afi_os.models import AuditLog, Campaign, Program, Project

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_domain_intake_retains_project_with_safe_unknown_defaults() -> None:
    response = client.post(
        "/api/portfolio/projects/intake",
        json={"domain": "https://www.bitget.com/affiliate", "actor": "Tran"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] is True
    assert result["warning_only"] is True
    assert result["permissions_changed"] is False
    assert result["campaign_state_changed"] is False
    assert result["google_ads_write"] is False
    assert result["project"]["domain"] == "bitget.com"
    assert result["project"]["brand_name"] == "Bitget"
    assert result["project"]["watch_status"] == WatchStatus.WATCH
    assert result["project"]["stage"] == ProjectStage.INTAKE
    assert result["project"]["registration_status"] == RegistrationStatus.NOT_STARTED
    assert result["project"]["program_id"] is None
    assert result["project"]["metrics"]["terms_status"]["value"] == "NOT_CHECKED"
    assert result["project"]["metrics"]["commission"]["value"] is None

    with SessionLocal() as db:
        project = db.scalar(select(Project).where(Project.domain == "bitget.com"))
        assert project is not None
        assert project.affiliate_program_found is False
        assert db.query(Program).count() == 0
        assert db.query(Campaign).count() == 0
        audit = db.scalar(
            select(AuditLog).where(AuditLog.entity_type == "project_intake")
        )
        assert audit is not None
        assert audit.payload_json["permissions_changed"] is False
        assert audit.payload_json["campaign_state_changed"] is False
        assert audit.payload_json["google_ads_write"] is False


def test_domain_intake_is_idempotent() -> None:
    first = client.post(
        "/api/portfolio/projects/intake", json={"domain": "bitget.com"}
    )
    second = client.post(
        "/api/portfolio/projects/intake", json={"domain": "www.bitget.com"}
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False
    assert second.json()["project"]["id"] == first.json()["project"]["id"]
    with SessionLocal() as db:
        assert db.query(Project).count() == 1
        assert db.query(AuditLog).filter_by(entity_type="project_intake").count() == 1


@pytest.mark.parametrize(
    "domain",
    ["localhost", "127.0.0.1", "bad domain.com", "https://user:pass@example.com"],
)
def test_domain_intake_rejects_invalid_hosts(domain: str) -> None:
    response = client.post(
        "/api/portfolio/projects/intake", json={"domain": domain}
    )

    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.query(Project).count() == 0


def test_portfolio_empty_state_offers_intake_instead_of_blank_table() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "apps" / "web" / "app.js").read_text(encoding="utf-8")

    assert 'request("/portfolio/projects/auto-check"' in script
    assert "Thêm dự án và bắt đầu rà nguồn" in script
    assert "PPC vẫn NOT_CHECKED" in script
    assert "data-project-intake" in script
    assert "Traffic/tháng" not in script
    assert 'name="source_url"' not in script
    assert 'name="observed_date"' not in script
