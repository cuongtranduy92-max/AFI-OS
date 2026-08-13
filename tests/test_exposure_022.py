from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import CommissionState, DataQuality
from afi_os.main import app
from afi_os.models import (
    AdsAccount,
    AffiliateNetwork,
    AuditLog,
    Campaign,
    CampaignDailyStat,
    CampaignProgramLink,
    Commission,
    CommissionFact,
    Conversion,
    Merchant,
    Program,
    Spend,
    SyncRun,
    TermsEvidence,
    TermsResearchRun,
)

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_data() -> None:
    with SessionLocal() as db:
        for model in (
            AuditLog,
            SyncRun,
            Commission,
            Conversion,
            CampaignDailyStat,
            Spend,
            CampaignProgramLink,
            Campaign,
            AdsAccount,
            TermsResearchRun,
            CommissionFact,
            TermsEvidence,
            Program,
            Merchant,
            AffiliateNetwork,
        ):
            db.execute(delete(model))
        db.commit()


def create_program(domain: str = "pictory.ai") -> dict:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": domain.split(".")[0].title(),
            "website_domain": domain,
            "program_name": f"{domain} Affiliate Program",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def campaign_csv(second_cost: str = "20") -> bytes:
    return (
        "Date,Customer ID,Account name,Campaign ID,Campaign,Campaign status,"
        "Campaign type,Currency code,Cost,Impressions,Clicks,Conversions\n"
        "2026-08-01,123-456-7890,Main Ads,9988,Pictory Search,ENABLED,Search,"
        "USD,10,1000,10,1\n"
        f"2026-08-02,123-456-7890,Main Ads,9988,Pictory Search,ENABLED,Search,"
        f"USD,{second_cost},2000,20,2\n"
    ).encode()


def google_ads_vi_csv() -> bytes:
    return (
        "Báo cáo chiến dịch\n"
        '"1 tháng 8, 2026 - 10 tháng 8, 2026"\n'
        "Ngày,Trạng thái chiến dịch,Chiến dịch,Mã đơn vị tiền tệ,"
        "Loại chiến dịch,Lượt chuyển đổi,Số lượt hiển thị,Lượt nhấp,Chi phí,"
        "ID Chiến Dịch\n"
        "2026-08-01,Đang bật,Pictory Search,VND,Tìm kiếm,0,1000,10,10,9988\n"
        "2026-08-02,Đang bật,Pictory Search,VND,Tìm kiếm,0,2000,20,20,9988\n"
        " --,Tổng số: Chiến dịch, --,VND, --,0,3000,30,30, --\n"
        "2026-08-02,Tổng số: Chiến dịch, --,VND, --,0,2000,20,20, --\n"
    ).encode()


def import_form(program_id: int, data: bytes, endpoint: str):
    return client.post(
        endpoint,
        data={
            "source": "GOOGLE_ADS_CSV",
            "account_external_id": "fallback-account",
            "account_name": "Fallback name",
            "default_program_id": str(program_id),
        },
        files={"file": ("campaigns.csv", data, "text/csv")},
    )


def test_terms_are_warnings_and_never_exclude_project_analysis() -> None:
    program = create_program()
    assert program["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    evaluated = client.post(
        "/api/compliance/evaluate",
        json={"program_id": program["id"]},
    )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["allowed"] is False
    assert evaluated.json()["status"] == "WARNING_TERMS_UNVERIFIED"
    assert evaluated.json()["project_included"] is True
    assert evaluated.json()["warning_only"] is True

    dashboard = client.get("/api/dashboard/summary").json()
    assert dashboard["programs"] == 1
    assert dashboard["programs_terms_ok"] == 0
    assert dashboard["programs_with_terms_warnings"] == 1


def test_google_ads_csv_is_idempotent_and_exposure_stays_warning_only() -> None:
    program = create_program()
    preview = import_form(
        program["id"],
        campaign_csv(),
        "/api/exposure/google-ads-import/preview",
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["new_rows"] == 2
    assert preview.json()["mapped_rows"] == 2
    assert preview.json()["totals_by_currency"] == {"USD": "30"}

    committed = import_form(
        program["id"],
        campaign_csv(),
        "/api/exposure/google-ads-import/commit",
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["rows_written"] == 2

    summary = client.get("/api/exposure/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["campaign_count"] == 1
    assert body["active_campaign_count"] == 1
    assert body["warning_campaign_count"] == 1
    assert body["currencies"][0]["total_spend"] == "30.000000"
    assert body["currencies"][0]["spend_at_risk"] == "30.000000"
    campaign = body["campaigns"][0]
    assert campaign["terms_warning_status"] == "WARNING_TERMS_UNVERIFIED"
    assert campaign["project_included"] is True
    assert campaign["clicks"] == 30
    assert campaign["impressions"] == 3000
    assert campaign["average_cpc"] == "1.000000"

    repeated = import_form(
        program["id"],
        campaign_csv(),
        "/api/exposure/google-ads-import/preview",
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["duplicates_existing"] == 2
    repeated_commit = import_form(
        program["id"],
        campaign_csv(),
        "/api/exposure/google-ads-import/commit",
    )
    assert repeated_commit.json()["rows_written"] == 0

    updated_preview = import_form(
        program["id"],
        campaign_csv("25"),
        "/api/exposure/google-ads-import/preview",
    )
    assert updated_preview.json()["update_rows"] == 1
    updated_commit = import_form(
        program["id"],
        campaign_csv("25"),
        "/api/exposure/google-ads-import/commit",
    )
    assert updated_commit.json()["rows_written"] == 1
    assert client.get("/api/exposure/summary").json()["currencies"][0][
        "total_spend"
    ] == "35.000000"

    acknowledged = client.post(
        f"/api/exposure/campaigns/{campaign['campaign_id']}/acknowledge",
        json={"actor": "Tran", "note": "Đã hiểu terms risk"},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["risk_acknowledged"] is True
    assert acknowledged.json()["terms_warning_status"] == "WARNING_TERMS_UNVERIFIED"
    stored_program = client.get("/api/programs").json()[0]
    assert stored_program["paid_search_permission"] == "NOT_CHECKED"


def test_google_ads_vietnamese_export_skips_preamble_and_total_rows() -> None:
    program = create_program()
    preview = client.post(
        "/api/exposure/google-ads-import/preview",
        data={
            "source": "GOOGLE_ADS_CSV_VI",
            "account_external_id": "123-456-7890",
            "account_name": "Google Ads",
            "default_program_id": str(program["id"]),
        },
        files={"file": ("bao-cao.csv", google_ads_vi_csv(), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["source"] == "GOOGLE_ADS_CSV"
    assert preview.json()["rows_read"] == 2
    assert preview.json()["valid_rows"] == 2
    assert preview.json()["error_count"] == 0
    assert preview.json()["totals_by_currency"] == {"VND": "30"}

    committed = client.post(
        "/api/exposure/google-ads-import/commit",
        data={
            "source": "GOOGLE_ADS_CSV_VI",
            "account_external_id": "123-456-7890",
            "account_name": "Google Ads",
            "default_program_id": str(program["id"]),
        },
        files={"file": ("bao-cao.csv", google_ads_vi_csv(), "text/csv")},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["rows_written"] == 2

    summary = client.get("/api/exposure/summary").json()
    assert summary["active_campaign_count"] == 1
    assert summary["campaigns"][0]["campaign_status"] == "ENABLED"
    assert summary["campaigns"][0]["channel_type"] == "SEARCH"
    assert summary["currencies"][0]["total_spend"] == "30.000000"

    repeated = client.post(
        "/api/exposure/google-ads-import/preview",
        data={
            "source": "GOOGLE_ADS_CSV",
            "account_external_id": "123-456-7890",
            "account_name": "Google Ads",
            "default_program_id": str(program["id"]),
        },
        files={"file": ("bao-cao.csv", google_ads_vi_csv(), "text/csv")},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["new_rows"] == 0
    assert repeated.json()["update_rows"] == 0
    assert repeated.json()["duplicates_existing"] == 2


def test_prohibited_campaign_is_included_and_financial_exposure_is_separate() -> None:
    program = create_program("risk.example")
    patched = client.patch(
        f"/api/programs/{program['id']}",
        json={"paid_search_permission": "PROHIBITED"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["gate_status"] == "WARNING_TERMS_PROHIBITED"

    imported = import_form(
        program["id"],
        campaign_csv(),
        "/api/exposure/google-ads-import/commit",
    )
    assert imported.status_code == 200, imported.text

    with SessionLocal() as db:
        conversion = Conversion(
            external_id="risk-order-1",
            program_id=program["id"],
            occurred_at=datetime.now(UTC),
            currency="USD",
            status="CONVERTED_PENDING",
            source="FIXTURE",
            raw_hash="risk-order-1-hash",
            quality=DataQuality.OBSERVED,
        )
        db.add(conversion)
        db.flush()
        db.add(
            Commission(
                external_id="risk-commission-1",
                conversion_id=conversion.id,
                amount=Decimal("50"),
                currency="USD",
                state=CommissionState.APPROVED,
                occurred_at=datetime.now(UTC),
                source="FIXTURE",
                quality=DataQuality.OBSERVED,
            )
        )
        db.commit()

    body = client.get("/api/exposure/summary").json()
    assert body["campaigns"][0]["terms_warning_status"] == "WARNING_TERMS_PROHIBITED"
    assert body["campaigns"][0]["project_included"] is True
    currency = body["currencies"][0]
    assert currency["total_spend"] == "30.000000"
    assert currency["spend_at_risk"] == "30.000000"
    assert currency["pending_commission_at_risk"] == "50.000000"
    assert currency["recognized_revenue"] == "50.000000"
    assert currency["cash_received"] == "0.000000"
    assert currency["actual_net_cash"] == "-30.000000"


def test_risk_exposure_ui_uses_warning_only_language() -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "DOT1.1 APPRAISAL · v0.2.102" in page.text
    assert 'src="/app.js?v=02102"' in page.text
    assert 'href="/styles.css?v=02102"' in page.text
    assert 'id="view-exposure"' in page.text
    assert "Mọi campaign vẫn được giữ lại" in page.text
    assert 'id="researchAttemptRows"' in page.text
    assert "Lịch sử rà Terms tự động" in page.text

    script = client.get("/app.js")
    assert script.status_code == 200
    assert "/exposure/google-ads-import/preview" in script.text
    assert "/exposure/google-ads-import/commit" in script.text
    assert "không phải bộ lọc loại trừ" in script.text
    assert "Tự ghép campaign" in script.text
    assert "/research-attempts" in script.text
    assert "function sourceAuthorityLabel(value)" in script.text
    assert 'PARTNER_PORTAL: "Cổng đối tác"' in script.text
    assert "item.source_authorities || {}" in script.text
    assert "result.source_authorities || {}" in script.text
    assert "PPC KHÔNG ĐỔI" in script.text
    assert "loadResearchAttempts(programId)" in script.text
