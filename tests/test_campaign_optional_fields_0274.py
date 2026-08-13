import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.models import AdsAccount, Campaign, Spend
from afi_os.services.ads_folder_import import import_downloaded_campaign_reports


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_campaign() -> int:
    with SessionLocal() as db:
        account = AdsAccount(
            external_id="123-456-7890",
            name="Primary Google Ads",
            currency="VND",
        )
        db.add(account)
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            external_id="24116162130",
            name="fliki.ai 10/8/2026 - 50$",
            status="PAUSED",
            channel_type="DISPLAY",
            daily_budget=Decimal("1300000"),
            currency="VND",
            launch_gate_status="WARNING_ONLY",
        )
        db.add(campaign)
        db.commit()
        return campaign.id


def _minimal_report(*, include_customer_id: bool) -> str:
    customer_header = ",Customer ID" if include_customer_id else ""
    customer_value = ",123-456-7890" if include_customer_id else ""
    return (
        "Date,Campaign ID,Campaign,Cost,Impressions,Clicks,Conversions"
        f"{customer_header}\n"
        "2026-08-11,24116162130,fliki.ai 10/8/2026 - 50$,"
        f"147920,1032,447,0{customer_value}\n"
    )


def _make_report_older_than_scan(report: Path) -> None:
    timestamp = datetime(2026, 8, 11, 13, 59, tzinfo=UTC).timestamp()
    os.utime(report, (timestamp, timestamp))


def test_explicit_customer_id_preserves_omitted_campaign_metadata(
    tmp_path: Path,
) -> None:
    campaign_id = _seed_campaign()
    report = tmp_path / "google-ads-campaign-report.csv"
    report.write_text(_minimal_report(include_customer_id=True), encoding="utf-8")
    _make_report_older_than_scan(report)

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
            min_age_seconds=0,
        )
        account = db.scalar(select(AdsAccount))
        campaign = db.get(Campaign, campaign_id)
        spend = db.scalar(select(Spend))

    identity = result["file_results"][0]["account_identity"]
    assert result["status"] == "SUCCESS"
    assert result["rows_written"] == 1
    assert identity["status"] == "VERIFIED_CUSTOMER_ID"
    assert identity["fallback_currency_rows"] == 1
    assert account is not None
    assert account.name == "Primary Google Ads"
    assert account.currency == "VND"
    assert campaign is not None
    assert campaign.status == "PAUSED"
    assert campaign.channel_type == "DISPLAY"
    assert campaign.daily_budget == Decimal("1300000")
    assert campaign.currency == "VND"
    assert campaign.launch_gate_status == "WARNING_ONLY"
    assert spend is not None
    assert spend.amount == Decimal("147920")
    assert spend.currency == "VND"


def test_single_account_fallback_requires_currency_on_every_row(
    tmp_path: Path,
) -> None:
    campaign_id = _seed_campaign()
    report = tmp_path / "google-ads-campaign-report.csv"
    report.write_text(_minimal_report(include_customer_id=False), encoding="utf-8")
    _make_report_older_than_scan(report)

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
            min_age_seconds=0,
        )
        campaign = db.get(Campaign, campaign_id)
        spend = db.scalar(select(Spend))

    identity = result["file_results"][0]["account_identity"]
    assert result["status"] == "PARTIAL"
    assert result["rows_written"] == 0
    assert result["files_account_mismatch"] == 1
    assert identity["status"] == "ACCOUNT_CURRENCY_REQUIRED"
    assert identity["fallback_currency_rows"] == 1
    assert campaign is not None
    assert campaign.daily_budget == Decimal("1300000")
    assert spend is None


def test_bootstrap_requires_currency_even_with_explicit_customer_id(
    tmp_path: Path,
) -> None:
    report = tmp_path / "google-ads-campaign-report.csv"
    report.write_text(_minimal_report(include_customer_id=True), encoding="utf-8")
    _make_report_older_than_scan(report)

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
            min_age_seconds=0,
        )
        account = db.scalar(select(AdsAccount))
        campaign = db.scalar(select(Campaign))

    identity = result["file_results"][0]["account_identity"]
    assert result["status"] == "PARTIAL"
    assert result["rows_written"] == 0
    assert identity["status"] == "ACCOUNT_CURRENCY_REQUIRED"
    assert account is None
    assert campaign is None
