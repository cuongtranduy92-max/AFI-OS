from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.api import camp_plans as camp_plans_api
from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import ProjectStage
from afi_os.main import app
from afi_os.models import AdsAccount, AdsAccountProjectHistory, Project
from afi_os.services.resource_rules import (
    AdsAccountInfo,
    EmailInfo,
    ResourceInfo,
    build_alerts,
    nurture_status,
    selectable_accounts,
)

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _email(
    age: int,
    *,
    email_id: int | None = None,
    device_changes: int = 0,
    history: tuple[str, ...] = (),
) -> EmailInfo:
    return EmailInfo(
        email_id=email_id or age + device_changes + 1,
        address=f"user-{age}-{device_changes}@example.com",
        created_at=datetime.now(UTC) - timedelta(days=age),
        declared_done=True,
        device_changes=device_changes,
        usage_history=history,
    )


def test_rule_engine_boundaries_and_all_alerts() -> None:
    today = date.today()
    assert nurture_status(_email(29, device_changes=4), today).is_chin is True
    interacting = nurture_status(_email(12, device_changes=1), today)
    assert interacting.stage == "INTERACTING"
    assert interacting.chin_eta_days == 11
    assert len(interacting.tasks_today) <= 3
    assert nurture_status(_email(1), today).stage == "SOAK"

    clean = _email(30, email_id=101)
    dirty = _email(30, email_id=102, history=("finance",))
    accounts = [
        AdsAccountInfo(account_id=1, email_id=clean.email_id, state="READY"),
        AdsAccountInfo(
            account_id=2,
            email_id=dirty.email_id,
            state="READY",
            project_ids=(10, 11),
            display_name="Ads lỗi",
        ),
    ]
    resources = [
        ResourceInfo(1, "paypal", "PayPal chính", 5200),
        ResourceInfo(2, "card", "Thẻ chính", 0, ("PayPal", "Wise"), "A"),
        ResourceInfo(3, "wise", "Wise", 0, (), "B"),
    ]
    codes = {
        item.code
        for item in build_alerts([clean, dirty], accounts, resources, 9, today)
    }
    assert {
        "ONE_ACCOUNT_ONE_PROJECT",
        "DIRTY_EMAIL_IN_USE",
        "EMAIL_SHORTAGE",
        "EMAIL_POOL_SMALL",
        "PAYPAL_CONCENTRATION",
        "CARD_MULTI_GATEWAY",
        "CONSISTENCY",
    } <= codes
    assert selectable_accounts([clean, dirty], accounts, today) == [1]


def test_resource_crud_nurture_and_secret_rejection() -> None:
    created = client.post(
        "/api/emails",
        json={
            "address": "Resource.User@Example.com",
            "created_at": (datetime.now(UTC) - timedelta(days=12)).isoformat(),
            "declared_done": True,
            "device_changes": 1,
            "usage_history": ["software"],
        },
    )
    assert created.status_code == 201
    email = created.json()
    assert email["address"] == "resource.user@example.com"
    assert email["nurture_status"]["chin_eta_days"] == 11

    secret = client.post(
        "/api/emails",
        json={"address": "secret@example.com", "password": "do-not-store"},
    )
    assert secret.status_code == 422
    assert client.post(
        "/api/ads-accounts",
        json={"type": "PERSONAL", "display_name": "   ", "password": "no"},
    ).status_code == 422
    assert client.post(
        "/api/resources", json={"type": "paypal", "label": "   "}
    ).status_code == 422

    tasks = email["nurture_status"]["tasks_today"]
    checked = client.post(
        f"/api/emails/{email['id']}/nurture-check",
        json={"tasks_done": tasks},
    )
    assert checked.status_code == 200
    assert checked.json()["nurture_status"]["tasks_done"] == tasks

    account = client.post(
        "/api/ads-accounts",
        json={
            "email_id": email["id"],
            "type": "INVOICE",
            "display_name": "Invoice 01",
            "state": "READY",
            "rent_cost": 25,
            "spend_fee_pct": 4.5,
        },
    )
    assert account.status_code == 201
    assert account.json()["selectable"] is False

    paypal = client.post(
        "/api/resources",
        json={"type": "paypal", "label": "PayPal chính", "monthly_in_usd": 5200},
    )
    assert paypal.status_code == 201
    overview = client.get("/api/resources/overview?planned_camps=5")
    assert overview.status_code == 200
    body = overview.json()
    assert body["stores_passwords"] is False
    assert body["planned_camps_source"] == "manual"
    assert "PAYPAL_CONCENTRATION" in {item["code"] for item in body["alerts"]}
    assert client.delete(f"/api/emails/{email['id']}").status_code == 409


def test_step_two_only_accepts_mature_clean_free_account(monkeypatch) -> None:
    project = Project(
        domain="resource-ready.example", brand_name="Resource", stage=ProjectStage.PREP
    )
    second = Project(domain="second-resource.example", brand_name="Second", stage=ProjectStage.PREP)
    with SessionLocal() as db:
        db.add_all([project, second])
        db.commit()
        project_id, second_id = project.id, second.id

    email = client.post(
        "/api/emails",
        json={
            "address": "mature@example.com",
            "created_at": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
            "declared_done": True,
            "usage_history": ["software"],
        },
    ).json()
    account_id = client.post(
        "/api/ads-accounts",
        json={
            "email_id": email["id"],
            "type": "PERSONAL",
            "display_name": "Ready account",
            "state": "READY",
        },
    ).json()["id"]
    assert [item["id"] for item in client.get("/api/ads-accounts/selectable").json()] == [
        account_id
    ]

    monkeypatch.setattr(
        camp_plans_api,
        "build_appraisal_contract",
        lambda db, item: SimpleNamespace(
            score=SimpleNamespace(pass_=True, total=100, flags=[])
        ),
    )
    generated = client.post(
        f"/api/projects/{project_id}/camp-plan/generate",
        json={
            "ref_url": "https://resource-ready.example/?ref=afi",
            "ads_account_id": account_id,
        },
    )
    assert generated.status_code == 200
    assert generated.json()["ads_account_id"] == account_id
    deployed = client.post(
        f"/api/projects/{project_id}/camp-plan/deploy", json={"actor": "resource-test"}
    )
    assert deployed.status_code == 200
    lineage = client.get("/api/resources/overview").json()["ads_accounts"][0]
    assert lineage["camp_plan_id"] == generated.json()["id"]
    assert lineage["camp_plan_status"] == "DEPLOYED"
    assert lineage["current_project_domain"] == "resource-ready.example"

    rejected = client.post(
        f"/api/projects/{second_id}/camp-plan/generate",
        json={
            "ref_url": "https://second-resource.example/?ref=afi",
            "ads_account_id": account_id,
        },
    )
    assert rejected.status_code == 409
    with SessionLocal() as db:
        account = db.get(AdsAccount, account_id)
        assert account is not None
        assert account.current_project_id == project_id
        history = db.scalar(
            select(AdsAccountProjectHistory).where(
                AdsAccountProjectHistory.ads_account_id == account_id,
                AdsAccountProjectHistory.project_id == project_id,
            )
        )
        assert history is not None


def test_resource_tab_exposes_security_note_forms_and_lineage() -> None:
    page = client.get("/")
    assert page.status_code == 200
    for marker in (
        'id="view-resources"',
        'id="resourceEmailForm"',
        'id="resourceAdsForm"',
        'id="resourceInventoryForm"',
        'id="resourceEmailRows"',
        'id="resourceAccountRows"',
        "App không lưu mật khẩu — dùng password manager.",
        "Lineage email → tài khoản Ads → dự án",
        "Bộ campaign",
    ):
        assert marker in page.text

    script = client.get("/app.js")
    assert script.status_code == 200
    for endpoint in (
        "/resources/overview",
        "/emails",
        "/ads-accounts",
        "/nurture-check",
    ):
        assert endpoint in script.text
