from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    CommissionType,
    DataQuality,
    EvidenceReviewStatus,
    PermissionStatus,
    ProgramStatus,
    ProjectStage,
    RegistrationStatus,
    SourceAuthority,
    WatchStatus,
)
from afi_os.main import app
from afi_os.models import (
    AdsAccount,
    AuditLog,
    Campaign,
    CampaignDailyStat,
    CommissionFact,
    Merchant,
    MetricSnapshot,
    Program,
    Project,
    Spend,
)

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_portfolio() -> tuple[int, int, int]:
    now = datetime(2026, 8, 12, 2, 30, tzinfo=UTC)
    with SessionLocal() as db:
        merchant = Merchant(name="Portfolio Fixture", website_domain="portfolio-0285.example")
        db.add(merchant)
        db.flush()
        program = Program(
            merchant_id=merchant.id,
            name="Portfolio Fixture Affiliate Program",
            signup_url="https://portfolio-0285.example/partners",
            status=ProgramStatus.PAUSED,
            paid_search_permission=PermissionStatus.NOT_CHECKED,
            brand_keyword_permission=PermissionStatus.NOT_CHECKED,
            non_brand_permission=PermissionStatus.NOT_CHECKED,
            direct_link_permission=PermissionStatus.NOT_CHECKED,
            trademark_in_ad_copy_permission=PermissionStatus.NOT_CHECKED,
        )
        db.add(program)
        db.flush()
        db.add(
            CommissionFact(
                program_id=program.id,
                source_url="https://portfolio-0285.example/commission",
                source_authority=SourceAuthority.OFFICIAL,
                excerpt="50 percent recurring for the lifetime of the customer.",
                checked_at=now,
                confidence=0.95,
                commission_type=CommissionType.RECURRING_LIFETIME,
                commission_rate=Decimal("0.50"),
                rate_is_maximum=False,
                applies_to="LIFETIME_RECURRING",
                review_status=EvidenceReviewStatus.ACCEPTED,
                evidence_hash="portfolio-0285-commission".ljust(64, "0"),
            )
        )
        project = Project(
            domain=merchant.website_domain,
            brand_name=merchant.name,
            affiliate_program_found=True,
            program_id=program.id,
            watch_status=WatchStatus.WATCH,
            stage=ProjectStage.PAUSED,
            registration_status=RegistrationStatus.BLOCKED_REGISTRATION,
            next_action="Keep the project and collect missing data",
        )
        db.add(project)
        db.flush()
        account = AdsAccount(
            external_id="123-456-7890",
            name="Portfolio Test Ads",
            currency="USD",
        )
        db.add(account)
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            project_id=project.id,
            external_id="0285001",
            name="Portfolio Search",
            status="ENABLED",
            channel_type="SEARCH",
            currency="USD",
        )
        db.add(campaign)
        db.flush()
        db.add(
            CampaignDailyStat(
                campaign_id=campaign.id,
                metric_date=date(2026, 8, 12),
                impressions=100,
                clicks=39,
                conversions=Decimal("1"),
                source="GOOGLE_ADS_CSV",
                quality=DataQuality.OBSERVED,
            )
        )
        db.add(
            Spend(
                campaign_id=campaign.id,
                spend_date=date(2026, 8, 12),
                amount=Decimal("12.50"),
                currency="USD",
                source="GOOGLE_ADS_CSV",
                quality=DataQuality.OBSERVED,
            )
        )
        for value, observed_at, suffix in (
            (Decimal("1000"), datetime(2026, 8, 10, tzinfo=UTC), "old"),
            (Decimal("1500"), now, "new"),
        ):
            db.add(
                MetricSnapshot(
                    project_id=project.id,
                    metric_key="keyword_monthly_searches",
                    numeric_value=value,
                    unit="searches/month",
                    quality=DataQuality.ESTIMATED,
                    source_name="Keyword research fixture",
                    source_url="https://portfolio-0285.example/keyword-source",
                    observed_at=observed_at,
                    confidence=0.7,
                    geography="GLOBAL",
                    language="en",
                    method_version="keyword-fixture-v1",
                    source_hash=f"portfolio-0285-keyword-{suffix}".ljust(64, "0"),
                    payload_json={"change_reason": "New source snapshot"},
                )
            )
        db.commit()
        return project.id, program.id, campaign.id


def test_portfolio_preserves_project_and_exposes_missing_as_unknown() -> None:
    project_id, _program_id, _campaign_id = _seed_portfolio()

    response = client.get("/api/portfolio/projects?risk=CTR_BELOW_40")

    assert response.status_code == 200, response.text
    item = next(row for row in response.json() if row["id"] == project_id)
    assert item["project_included"] is True
    assert item["opportunity_potential"] is None
    assert item["opportunity_state"] == "DATA_INCOMPLETE"
    assert item["metrics"]["independent_advertisers"]["value"] is None
    assert item["metrics"]["independent_advertisers"]["quality"] == "UNKNOWN"
    assert item["metrics"]["ctr"]["value"] == 39.0
    assert item["metrics"]["cost"]["value"] == 12.5
    assert item["metrics"]["commission"]["value"] == 50.0
    assert item["commission_state"] == "RESOLVED"
    assert "REGISTRATION_BLOCKED" in item["risk_badges"]
    assert "PPC_NOT_CHECKED" in item["risk_badges"]
    assert "CTR_BELOW_40" in item["risk_badges"]


def test_truth_endpoint_keeps_source_lineage_and_previous_value() -> None:
    project_id = client.get("/api/portfolio/projects").json()[0]["id"]

    commission = client.get(f"/api/portfolio/projects/{project_id}/truth/commission")
    keyword = client.get(
        f"/api/portfolio/projects/{project_id}/truth/keyword_monthly_searches"
    )

    assert commission.status_code == 200, commission.text
    assert commission.json()["source_url"].endswith("/commission")
    assert commission.json()["lineage"][0]["review_status"] == "ACCEPTED"
    assert keyword.status_code == 200, keyword.text
    assert keyword.json()["value"] == 1500.0
    assert keyword.json()["previous_value"] == 1000.0
    assert keyword.json()["quality"] == "ESTIMATED"
    assert keyword.json()["geography"] == "GLOBAL"
    assert keyword.json()["language"] == "en"


def test_workflow_update_is_audited_without_mutating_program_or_campaign() -> None:
    item = client.get("/api/portfolio/projects").json()[0]
    project_id = item["id"]
    program_id = item["program_id"]
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        campaign = db.scalar(select(Campaign).where(Campaign.project_id == project_id))
        assert program is not None and campaign is not None
        permissions_before = (
            program.paid_search_permission,
            program.brand_keyword_permission,
            program.non_brand_permission,
            program.direct_link_permission,
            program.trademark_in_ad_copy_permission,
        )
        program_status_before = program.status
        campaign_status_before = campaign.status

    updated = client.patch(
        f"/api/portfolio/projects/{project_id}/workflow",
        json={
            "stage": "EVALUATION",
            "registration_status": "BLOCKED_REGISTRATION",
            "owner": "Portfolio QA",
            "next_action": "Collect international keyword data",
            "actor": "Portfolio Test",
        },
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["stage"] == "EVALUATION"
    assert updated.json()["owner"] == "Portfolio QA"
    assert updated.json()["project_included"] is True
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        campaign = db.scalar(select(Campaign).where(Campaign.project_id == project_id))
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "project_workflow",
                AuditLog.entity_id == str(project_id),
            )
            .order_by(AuditLog.id.desc())
        )
        assert program is not None and campaign is not None and audit is not None
        assert (
            program.paid_search_permission,
            program.brand_keyword_permission,
            program.non_brand_permission,
            program.direct_link_permission,
            program.trademark_in_ad_copy_permission,
        ) == permissions_before
        assert program.status == program_status_before
        assert campaign.status == campaign_status_before
        assert audit.actor == "Portfolio Test"
        assert audit.payload_json["warning_only"] is True
        assert audit.payload_json["google_ads_write"] is False


def test_radar_uses_missing_instead_of_fake_zero() -> None:
    response = client.get("/api/ad-intelligence/radar")

    assert response.status_code == 200, response.text
    item = next(
        row for row in response.json() if row["domain"] == "portfolio-0285.example"
    )
    assert item["distinct_advertisers"] is None
    assert item["top_advertiser_share"] is None
    assert item["independent_advertiser_score"] is None
    assert item["score_label"] == "DATA_MISSING"
