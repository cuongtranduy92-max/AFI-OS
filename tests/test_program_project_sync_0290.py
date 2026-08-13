from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    PermissionStatus,
    ProgramStatus,
    ProjectStage,
    RegistrationStatus,
    WatchStatus,
)
from afi_os.main import app
from afi_os.models import AuditLog, Merchant, Program, Project
from afi_os.services.project_sync import ensure_project_for_program, sync_program_projects
from afi_os.services.terms_research import _find_or_create_program

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_program_api_immediately_creates_filterable_portfolio_project() -> None:
    created = client.post(
        "/api/programs",
        json={
            "merchant_name": "Snov",
            "website_domain": "snov.io",
            "program_name": "Snov Affiliate Program",
        },
    )
    filtered = client.get("/api/portfolio/projects?query=snov.io")

    assert created.status_code == 200, created.text
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()) == 1
    item = filtered.json()[0]
    assert item["domain"] == "snov.io"
    assert item["program_id"] == created.json()["id"]
    assert item["stage"] == "RESEARCH"
    assert item["registration_status"] == "NOT_STARTED"
    assert item["project_included"] is True
    assert "PPC_NOT_CHECKED" in item["risk_badges"]


def test_terms_discovery_also_retains_program_in_portfolio() -> None:
    with SessionLocal() as db:
        program = _find_or_create_program(db, "research-only.example")
        db.commit()
        project = db.scalar(
            select(Project).where(Project.domain == "research-only.example")
        )
        assert project is not None
        assert project.program_id == program.id
        assert project.stage == ProjectStage.RESEARCH
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED


def test_sync_links_existing_project_without_overwriting_operator_workflow() -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Existing", website_domain="existing-project.example")
        db.add(merchant)
        db.flush()
        program = Program(
            merchant_id=merchant.id,
            name="Existing Affiliate Program",
            status=ProgramStatus.DISCOVERED,
        )
        project = Project(
            domain=merchant.website_domain,
            brand_name=merchant.name,
            affiliate_program_found=False,
            watch_status=WatchStatus.HIGH_VALUE,
            stage=ProjectStage.EVALUATION,
            registration_status=RegistrationStatus.BLOCKED_REGISTRATION,
            owner="Operator",
            next_action="Keep this workflow",
        )
        db.add_all([program, project])
        db.commit()

        linked, result = ensure_project_for_program(db, program)
        db.commit()
        assert result == "LINKED"
        assert linked.program_id == program.id
        assert linked.affiliate_program_found is True
        assert linked.stage == ProjectStage.EVALUATION
        assert linked.registration_status == RegistrationStatus.BLOCKED_REGISTRATION
        assert linked.owner == "Operator"
        assert linked.next_action == "Keep this workflow"
        audit = db.scalar(
            select(AuditLog).where(AuditLog.entity_type == "project_program_sync")
        )
        assert audit is not None
        assert audit.payload_json["workflow_preserved"] is True
        assert audit.payload_json["google_ads_write"] is False


def test_periodic_sync_heals_missing_project_once_and_is_idempotent() -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Heal", website_domain="heal-project.example")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Heal Affiliate Program")
        db.add(program)
        db.commit()

        first = sync_program_projects(db)
        db.commit()
        second = sync_program_projects(db)
        db.commit()

        assert first == {"scanned": 1, "created": 1, "linked": 0, "preserved": 0}
        assert second == {"scanned": 1, "created": 0, "linked": 0, "preserved": 1}
        assert db.scalar(select(Project).where(Project.domain == merchant.website_domain))
        assert db.query(Project).count() == 1
