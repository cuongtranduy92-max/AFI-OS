from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.api import camp_plans as camp_plans_api
from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AuditAction, CampPlanStatus, ProjectStage
from afi_os.main import app
from afi_os.models import AuditLog, CampPlan, Project

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_projects() -> tuple[int, int]:
    with SessionLocal() as db:
        passed = Project(
            domain="fliki.ai",
            brand_name="Fliki",
            stage=ProjectStage.PREP,
        )
        failed = Project(
            domain="not-ready.example",
            brand_name="Not Ready",
            stage=ProjectStage.EVALUATION,
        )
        db.add_all([passed, failed])
        db.commit()
        return passed.id, failed.id


def _appraisal(project: Project) -> SimpleNamespace:
    is_pass = project.domain == "fliki.ai"
    return SimpleNamespace(
        score=SimpleNamespace(
            pass_=is_pass,
            total=100 if is_pass else 35,
            flags=[],
        )
    )


def test_generate_relint_deploy_and_audit(monkeypatch) -> None:
    passed_id, _ = _seed_projects()
    monkeypatch.setattr(
        camp_plans_api,
        "build_appraisal_contract",
        lambda db, project: _appraisal(project),
    )
    ref_url = "https://fliki.ai/?via=afi-os"

    generated = client.post(
        f"/api/projects/{passed_id}/camp-plan/generate",
        json={"ref_url": ref_url},
    )
    assert generated.status_code == 200
    body = generated.json()
    plan = body["plan"]
    assert body["status"] == "DRAFT"
    assert body["google_ads_write"] is False
    assert len(plan["headlines"]) == 15
    assert len(plan["descriptions"]) == 4
    assert len(plan["sitelinks"]) == 4
    assert len(plan["callouts"]) == 4
    assert 2 <= sum("fliki.ai" in item.lower() for item in plan["headlines"]) <= 3
    assert sum("fliki.ai" in item.lower() for item in plan["descriptions"]) == 1
    assert all(item["final_url"] == ref_url for item in plan["sitelinks"])
    assert all(len(item) <= 30 for item in plan["headlines"])
    assert all(len(item) <= 90 for item in plan["descriptions"])
    assert all(len(item["label"]) <= 25 for item in plan["sitelinks"])
    assert all(len(item) <= 25 for item in plan["callouts"])

    edited = {**plan, "headlines": list(plan["headlines"])}
    edited["headlines"][3] = "Free Best Fliki"
    relinted = client.post(
        f"/api/projects/{passed_id}/camp-plan/generate",
        json={"ref_url": ref_url, "existing_plan": edited},
    )
    assert relinted.status_code == 200
    issues = relinted.json()["linter"]
    row_errors = [
        item
        for item in issues
        if item["level"] == "error"
        and item["section"] == "headlines"
        and item["index"] == 3
    ]
    assert {"free", "best"} <= {
        term
        for item in row_errors
        for term in ("free", "best")
        if f"'{term}'" in item["message"]
    }

    blocked = client.post(
        f"/api/projects/{passed_id}/camp-plan/deploy",
        json={"actor": "test-operator"},
    )
    assert blocked.status_code == 409

    fixed = client.post(
        f"/api/projects/{passed_id}/camp-plan/generate",
        json={"ref_url": ref_url, "existing_plan": plan},
    )
    assert fixed.status_code == 200
    assert fixed.json()["has_errors"] is False

    deployed = client.post(
        f"/api/projects/{passed_id}/camp-plan/deploy",
        json={"actor": "test-operator"},
    )
    assert deployed.status_code == 200
    assert deployed.json()["status"] == "DEPLOYED"

    fetched = client.get(f"/api/projects/{passed_id}/camp-plan")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "DEPLOYED"
    with SessionLocal() as db:
        saved = db.scalar(select(CampPlan).where(CampPlan.project_id == passed_id))
        assert saved is not None and saved.status == CampPlanStatus.DEPLOYED
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "camp_plan",
                AuditLog.entity_id == str(saved.id),
                AuditLog.action == AuditAction.APPROVE,
            )
        )
        assert audit is not None
        assert audit.payload_json["google_ads_write"] is False


def test_non_pass_project_is_blocked_and_eligible_list_is_truthful(monkeypatch) -> None:
    passed_id, failed_id = _seed_projects()
    monkeypatch.setattr(
        camp_plans_api,
        "build_appraisal_contract",
        lambda db, project: _appraisal(project),
    )

    response = client.post(
        f"/api/projects/{failed_id}/camp-plan/generate",
        json={"ref_url": "https://not-ready.example/ref"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["score_pass"] is False

    eligible = client.get("/api/projects/camp-plan/eligible")
    assert eligible.status_code == 200
    assert [item["project_id"] for item in eligible.json()] == [passed_id]


def test_missing_plan_and_credential_urls_are_rejected(monkeypatch) -> None:
    passed_id, _ = _seed_projects()
    monkeypatch.setattr(
        camp_plans_api,
        "build_appraisal_contract",
        lambda db, project: _appraisal(project),
    )
    assert client.get(f"/api/projects/{passed_id}/camp-plan").status_code == 404
    invalid = client.post(
        f"/api/projects/{passed_id}/camp-plan/generate",
        json={"ref_url": "https://user:secret@fliki.ai/ref"},
    )
    assert invalid.status_code == 422
