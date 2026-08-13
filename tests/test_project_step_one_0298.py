from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    AdvertiserClassification,
    AuditAction,
    CommissionType,
    DataQuality,
    EvidenceReviewStatus,
    PermissionStatus,
    ProgramStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import (
    AdObservation,
    Advertiser,
    AuditLog,
    CommissionFact,
    Merchant,
    MetricSnapshot,
    Offer,
    Program,
    Project,
    TermsEvidence,
)
from afi_os.services import project_check

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _snapshot(
    project_id: int,
    key: str,
    value: Decimal,
    unit: str,
    suffix: str,
) -> MetricSnapshot:
    return MetricSnapshot(
        project_id=project_id,
        metric_key=key,
        numeric_value=value,
        unit=unit,
        quality=DataQuality.ESTIMATED,
        source_name="Source-backed Step 1 fixture",
        source_url=f"https://source.example/{suffix}",
        observed_at=datetime(2026, 8, 13, tzinfo=UTC),
        confidence=0.9,
        geography="GLOBAL",
        language="en",
        method_version="step-one-fixture-v1",
        source_hash=f"step-one-{suffix}".ljust(64, "0"),
    )


def _seed_complete_project() -> tuple[int, int]:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    with SessionLocal() as db:
        merchant = Merchant(name="Step One", website_domain="step-one.example")
        db.add(merchant)
        db.flush()
        program = Program(
            merchant_id=merchant.id,
            name="Step One Affiliate",
            signup_url="https://step-one.example/affiliate",
            dashboard_url="https://partners.step-one.example/login",
            status=ProgramStatus.ACTIVE,
        )
        db.add(program)
        db.flush()
        for index, price in enumerate((Decimal("10"), Decimal("20"), Decimal("30")), 1):
            db.add(
                Offer(
                    program_id=program.id,
                    external_id=f"plan-{index}",
                    name=f"Plan {index}",
                    price=price,
                    currency="USD",
                    commission_type=CommissionType.RECURRING_LIFETIME,
                    source_url=f"https://step-one.example/pricing#plan-{index}",
                )
            )
        db.add(
            CommissionFact(
                program_id=program.id,
                source_url="https://step-one.example/affiliate-terms",
                source_authority=SourceAuthority.OFFICIAL,
                excerpt="50% recurring commission for the lifetime of the customer.",
                checked_at=now,
                confidence=0.95,
                commission_type=CommissionType.RECURRING_LIFETIME,
                commission_rate=Decimal("0.50"),
                rate_is_maximum=False,
                applies_to="CORE_AFFILIATE_COMMISSION",
                review_status=EvidenceReviewStatus.ACCEPTED,
                evidence_hash="step-one-commission".ljust(64, "0"),
            )
        )
        db.add(
            TermsEvidence(
                program_id=program.id,
                source_url="https://step-one.example/affiliate-terms",
                excerpt="Paid search advertising is prohibited.",
                evidence_hash="step-one-terms".ljust(64, "0"),
                checked_at=now,
                confidence=0.95,
                decision=PermissionStatus.PROHIBITED,
                scope="PAID_SEARCH",
                applies_to="PAID_SEARCH",
                review_status=EvidenceReviewStatus.ACCEPTED,
                source_authority=SourceAuthority.OFFICIAL,
            )
        )
        project = Project(
            domain=merchant.website_domain,
            brand_name=merchant.name,
            category="SaaS",
            affiliate_program_found=True,
            program_id=program.id,
        )
        db.add(project)
        db.flush()
        db.add_all(
            [
                _snapshot(
                    project.id,
                    "website_traffic_monthly",
                    Decimal("25000"),
                    "visits/month",
                    "traffic",
                ),
                _snapshot(
                    project.id,
                    "primary_keyword_search_volume",
                    Decimal("3000"),
                    "searches/month",
                    "volume",
                ),
                _snapshot(
                    project.id,
                    "primary_keyword_bid_low",
                    Decimal("0.10"),
                    "USD/click",
                    "bid-low",
                ),
                _snapshot(
                    project.id,
                    "primary_keyword_bid_high",
                    Decimal("0.20"),
                    "USD/click",
                    "bid-high",
                ),
            ]
        )
        advertiser = Advertiser(
            external_key="AR-STEP-ONE",
            verified_name="Step One Advertiser",
            classification=AdvertiserClassification.AFFILIATE_OR_PUBLISHER,
            confidence=0.9,
        )
        db.add(advertiser)
        db.flush()
        db.add(
            AdObservation(
                advertiser_id=advertiser.id,
                project_id=project.id,
                source_url="https://adstransparency.google.com/advertiser/AR-STEP-ONE",
                landing_domain=project.domain,
                snapshot_date=date(2026, 8, 13),
                content_hash="step-one-observation".ljust(64, "0"),
                metadata_json={
                    "source_name": "Google Ads Transparency",
                    "source_authority": "THIRD_PARTY",
                    "result_set_complete": True,
                    "confidence": 0.9,
                    "evidence_type": "ADVERTISER_RESULT_SET",
                },
            )
        )
        db.commit()
        return project.id, program.id


def test_step_one_returns_source_backed_numbers_and_exact_payback_formula() -> None:
    project_id, _program_id = _seed_complete_project()

    response = client.get(f"/api/portfolio/projects/{project_id}/step-one")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fields"]["website_traffic_monthly"]["value"] == 25000.0
    assert body["fields"]["primary_keyword_search_volume"]["value"] == 3000.0
    assert body["fields"]["average_package_price"]["value"] == 20.0
    assert body["fields"]["accepted_commission_rate"]["value"] == 50.0
    assert body["fields"]["estimated_commission_per_buyer"]["value"] == 10.0
    assert body["fields"]["estimated_payback_days_low_bid"]["value"] == 135.0
    assert body["fields"]["estimated_payback_days_high_bid"]["value"] == 45.0
    assert body["permissions"]["PAID_SEARCH"] == "PROHIBITED"
    assert body["warning_only"] is True
    assert body["project_included"] is True
    assert body["decision_ready"] is True
    assert body["readiness"] == "READY_FOR_STEP_2"


def test_step_one_payback_matches_original_sheet_with_fixed_vnd_usd_fx(monkeypatch) -> None:
    with SessionLocal() as db:
        project_id = db.scalar(select(Project.id).where(Project.domain == "step-one.example"))
    assert project_id is not None
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        assert project is not None
        snapshots = {item.metric_key: item for item in project.metric_snapshots}
        snapshots["primary_keyword_bid_low"].numeric_value = Decimal("11000")
        snapshots["primary_keyword_bid_low"].unit = "VND/click"
        snapshots["primary_keyword_bid_high"].numeric_value = Decimal("49000")
        snapshots["primary_keyword_bid_high"].unit = "VND/click"
        offers = list(project.program.offers)
        for offer in offers:
            offer.price = Decimal("111.7")
        fact = project.program.commission_facts[0]
        fact.commission_rate = Decimal("0.30")
        db.commit()

    response = client.get(f"/api/portfolio/projects/{project_id}/step-one")

    assert response.status_code == 200, response.text
    fields = response.json()["fields"]
    assert fields["estimated_commission_per_buyer"]["value"] == 33.51
    assert fields["estimated_payback_days_low_bid"]["value"] == 170.4
    assert fields["estimated_payback_days_high_bid"]["value"] == 126.5
    assert "26.000" in fields["estimated_payback_days_low_bid"]["note"]

    monkeypatch.setattr(project_check, "PAYBACK_FX_VND_PER_USD", Decimal("13000"))
    changed = client.get(f"/api/portfolio/projects/{project_id}/step-one").json()["fields"]
    assert changed["estimated_payback_days_low_bid"]["value"] == 340.9
    assert changed["estimated_payback_days_high_bid"]["value"] == 253.1


def test_step_one_missing_project_lists_exact_api_needs_and_blocks_transition() -> None:
    created = client.post(
        "/api/portfolio/projects/intake",
        json={"domain": "missing-step-one.example", "actor": "test"},
    ).json()
    project_id = created["project"]["id"]

    check = client.get(f"/api/portfolio/projects/{project_id}/step-one")
    transition = client.post(
        f"/api/portfolio/projects/{project_id}/step-one-decision",
        json={"decision": "PREPARE_STEP_2", "actor": "test"},
    )

    assert check.status_code == 200, check.text
    body = check.json()
    assert body["decision_ready"] is False
    assert body["fields"]["website_traffic_monthly"]["value"] is None
    assert body["fields"]["estimated_payback_days_high_bid"]["value"] is None
    required = {item["group"]: item["source_required"] for item in body["collection_needs"]}
    assert "Similarweb API" in required["Traffic thị trường"]
    assert "Google Ads Keyword Planner/API" in required["Từ khóa & CPC"]
    assert "partner portal" in required["Affiliate account"]
    assert transition.status_code == 409
    assert "blocking_fields" in transition.json()["detail"]


def test_step_one_decision_saves_snapshot_and_exposes_project_in_step_two() -> None:
    project = next(
        item
        for item in client.get("/api/portfolio/projects").json()
        if item["domain"] == "step-one.example"
    )
    project_id = project["id"]
    program_id = project["program_id"]
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        permissions_before = (
            program.paid_search_permission,
            program.brand_keyword_permission,
            program.non_brand_permission,
            program.direct_link_permission,
        )

    response = client.post(
        f"/api/portfolio/projects/{project_id}/step-one-decision",
        json={"decision": "PREPARE_STEP_2", "actor": "Step One QA"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["project"]["stage"] == "PREP"
    assert response.json()["campaign_state_changed"] is False
    assert response.json()["permissions_changed"] is False
    assert response.json()["google_ads_write"] is False
    step_two = client.get("/api/portfolio/projects?stage=PREP").json()
    assert any(item["id"] == project_id for item in step_two)
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "project_step_one_decision",
                AuditLog.entity_id == str(project_id),
                AuditLog.action == AuditAction.UPDATE,
            )
            .order_by(AuditLog.id.desc())
        )
        assert program is not None and audit is not None
        assert permissions_before == (
            program.paid_search_permission,
            program.brand_keyword_permission,
            program.non_brand_permission,
            program.direct_link_permission,
        )
        assert audit.payload_json["step_one_snapshot"]["decision_ready"] is True
        assert audit.payload_json["google_ads_write"] is False


def test_step_one_ui_has_numbers_sources_api_needs_and_step_two_queue() -> None:
    page = client.get("/").text
    script = client.get("/app.js").text

    assert "Bước 2 · Sinh và kiểm tra nội dung campaign" in page
    assert 'id="stepTwoProjectRows"' in page
    assert "Hoàn vốn ước tính" in script
    assert "Nguồn/API cần triển khai" in script
    assert "Không có nguồn thì hiện yêu cầu API" in script
    assert 'data-step-one-decision="PREPARE_STEP_2"' in script
    assert "/step-one-decision" in script
    assert 'id="projectTrafficForm"' not in script
    assert "Không cần nhập traffic, ngày hay URL nguồn" in script
    assert "/portfolio/projects/auto-check" in script


def test_source_backed_manual_traffic_updates_step_one_and_deduplicates() -> None:
    created = client.post(
        "/api/portfolio/projects/intake",
        json={"domain": "manual-traffic.example", "actor": "test"},
    ).json()
    project_id = created["project"]["id"]
    observed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    payload = {
        "website_traffic_monthly": "25432",
        "source_name": "Similarweb manual check",
        "source_url": "https://www.similarweb.com/website/manual-traffic.example/",
        "observed_at": observed_at,
        "geography": "GLOBAL",
        "note": "Manual check for Step 1",
        "actor": "Traffic QA",
    }

    first = client.post(
        f"/api/portfolio/projects/{project_id}/traffic-snapshots", json=payload
    )
    duplicate = client.post(
        f"/api/portfolio/projects/{project_id}/traffic-snapshots", json=payload
    )

    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["google_ads_write"] is False
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["created"] is False
    assert duplicate.json()["snapshot_id"] == first.json()["snapshot_id"]
    field = duplicate.json()["step_one"]["fields"]["website_traffic_monthly"]
    assert field["value"] == 25432.0
    assert field["collection_state"] == "AVAILABLE"
    assert field["quality"] == "IMPORTED"
    assert field["source_url"] == payload["source_url"]
    with SessionLocal() as db:
        snapshots = list(
            db.scalars(
                select(MetricSnapshot).where(
                    MetricSnapshot.project_id == project_id,
                    MetricSnapshot.metric_key == "website_traffic_monthly",
                )
            ).all()
        )
        audits = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "project_metric_snapshot",
                    AuditLog.entity_id == str(first.json()["snapshot_id"]),
                )
            ).all()
        )
        assert len(snapshots) == 1
        assert len(audits) == 1
        assert audits[0].payload_json["google_ads_write"] is False


def test_manual_traffic_rejects_missing_or_non_http_source() -> None:
    project_id = client.post(
        "/api/portfolio/projects/intake",
        json={"domain": "bad-traffic.example", "actor": "test"},
    ).json()["project"]["id"]
    response = client.post(
        f"/api/portfolio/projects/{project_id}/traffic-snapshots",
        json={
            "website_traffic_monthly": 10000,
            "source_name": "Unverifiable input",
            "source_url": "not-a-url",
            "observed_at": datetime.now(UTC).isoformat(),
            "geography": "GLOBAL",
            "actor": "Traffic QA",
        },
    )

    assert response.status_code == 422
