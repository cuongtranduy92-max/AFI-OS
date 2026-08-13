from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.main import app
from afi_os.models import (
    AdsAccount,
    Campaign,
    CampaignDailyStat,
    CampaignProgramLink,
    CampDiagnosis,
    Merchant,
    Program,
    Spend,
    SyncRun,
)
from afi_os.services.campaign_diagnosis import _cost_usd
from afi_os.services.google_ads_api import build_campaign_detail_queries

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_campaign(*, with_ref_feed: bool = False) -> int:
    with SessionLocal() as db:
        account = AdsAccount(
            external_id="370-734-2176",
            name="Google Ads chính",
            currency="USD",
        )
        merchant = Merchant(name="Fliki", website_domain="fliki.ai")
        program = Program(merchant=merchant, name="Fliki Affiliate")
        db.add_all([account, program])
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            external_id="9988776655",
            name="Fliki Brand",
            status="ENABLED",
            channel_type="SEARCH",
            currency="USD",
            created_at=datetime.now(UTC) - timedelta(days=10),
        )
        db.add(campaign)
        db.flush()
        db.add(CampaignProgramLink(campaign_id=campaign.id, program_id=program.id))
        db.add(
            CampaignDailyStat(
                campaign_id=campaign.id,
                metric_date=date.today() - timedelta(days=2),
                impressions=100,
                clicks=30,
                conversions=Decimal("0"),
                source="GOOGLE_ADS_API",
            )
        )
        db.add(
            Spend(
                campaign_id=campaign.id,
                spend_date=date.today() - timedelta(days=2),
                amount=Decimal("5"),
                currency="USD",
                source="GOOGLE_ADS_API",
            )
        )
        if with_ref_feed:
            db.add(
                SyncRun(
                    connector="AFFILIATE_COMMISSION_FOLDER",
                    started_at=datetime.now(UTC),
                    ended_at=datetime.now(UTC),
                    status="SUCCESS",
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "file_results": [
                            {"program_id": program.id, "status": "UP_TO_DATE"}
                        ]
                    },
                )
            )
        db.commit()
        return campaign.id


def test_detail_query_set_is_complete_and_read_only() -> None:
    queries = build_campaign_detail_queries(
        customer_id="370-734-2176",
        campaign_external_id="9988776655",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 13),
    )
    assert set(queries) == {
        "keywords",
        "search_terms",
        "devices",
        "geography",
        "ages",
        "genders",
        "ads",
        "change_events",
    }
    joined = " ".join(queries.values()).lower()
    for resource in (
        "keyword_view",
        "search_term_view",
        "segments.device",
        "geographic_view",
        "age_range_view",
        "gender_view",
        "ad_group_ad",
        "change_event",
    ):
        assert resource in joined
    assert all(word not in joined.upper() for word in ("MUTATE", "UPDATE ", "REMOVE "))


def test_list_and_detail_keep_missing_ref_null_and_store_history() -> None:
    campaign_id = _seed_campaign()
    listed = client.get("/api/campaigns/diagnoses")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["warning_only"] is True
    assert payload["google_ads_write_operations_enabled"] is False
    item = payload["campaigns"][0]
    assert item["refs"] is None
    assert item["cost_per_ref"] is None
    assert item["ref_data_status"] == "MISSING_AFFILIATE_FEED"

    detail = client.get(f"/api/campaigns/{campaign_id}/diagnosis?refresh=false")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["refs"] is None
    assert body["google_ads_write_operations_enabled"] is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count(CampDiagnosis.id))) == 1


def test_confirmed_empty_affiliate_feed_is_zero_but_not_a_stop_signal() -> None:
    campaign_id = _seed_campaign(with_ref_feed=True)
    result = client.get(f"/api/campaigns/{campaign_id}/diagnosis?refresh=false")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["refs"] == 0
    codes = {item["code"] for item in body["findings"]}
    assert "TOO_EARLY" in codes
    assert "NO_REF_AFTER_CLICKS" not in codes


def test_cost_per_ref_uses_fixed_payback_fx_and_ignores_finance_ledger() -> None:
    campaign_id = _seed_campaign()
    with SessionLocal() as db:
        campaign = db.get(Campaign, campaign_id)
        assert campaign is not None
        spend = campaign.spends[0]
        spend.amount = Decimal("260000")
        spend.currency = "VND"
        # Deliberately conflicting Page 4 normalization must not affect $/ref.
        spend.normalized_amount = Decimal("999")
        spend.normalized_currency = "USD"
        db.commit()

        value, status = _cost_usd(campaign)

    assert value == 10.0
    assert status == "FIXED_PAYBACK_FX:26000 VND/USD"


def test_cost_per_ref_does_not_use_ledger_for_other_currencies() -> None:
    campaign_id = _seed_campaign()
    with SessionLocal() as db:
        campaign = db.get(Campaign, campaign_id)
        assert campaign is not None
        spend = campaign.spends[0]
        spend.amount = Decimal("10")
        spend.currency = "EUR"
        spend.normalized_amount = Decimal("11")
        spend.normalized_currency = "USD"
        db.commit()

        value, status = _cost_usd(campaign)

    assert value is None
    assert status == "UNSUPPORTED_COST_CURRENCY:EUR"


def test_ui_exposes_page_three_without_google_ads_write_controls() -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert 'data-view="doctor"' in page.text
    assert 'id="view-doctor"' in page.text
    assert "GOOGLE ADS · CHỈ ĐỌC" in page.text
    assert "Mở chẩn đoán" in page.text
