import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.models import AdsAccount, Campaign, CampaignDailyStat, Spend
from afi_os.services.ads_folder_import import import_downloaded_campaign_reports


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_campaigns(*, names: list[str]) -> list[int]:
    with SessionLocal() as db:
        account = AdsAccount(
            external_id="123-456-7890",
            name="Google Ads",
            currency="VND",
        )
        db.add(account)
        db.flush()
        campaigns = [
            Campaign(
                ads_account_id=account.id,
                external_id=str(24116162130 + index),
                name=name,
                status="PAUSED",
                channel_type="SEARCH",
                daily_budget=Decimal("1300000"),
                currency="VND",
                launch_gate_status="WARNING_ONLY",
            )
            for index, name in enumerate(names)
        ]
        db.add_all(campaigns)
        db.commit()
        return [campaign.id for campaign in campaigns]


def _report(*, customer_id: str, campaign_name: str) -> str:
    return (
        "Date,Customer ID,Campaign,Cost,Impressions,Clicks,Conversions\n"
        f"2026-08-11,{customer_id},{campaign_name},147920,1032,447,0\n"
    )


def _write_report(path: Path, content: str, now: datetime) -> None:
    path.write_text(content, encoding="utf-8")
    stable = now.timestamp() - 60
    os.utime(path, (stable, stable))


def test_renamed_report_recovers_campaign_id_from_exact_account_name(
    tmp_path: Path,
) -> None:
    campaign_name = "fliki.ai 10/8/2026 - 50$"
    campaign_id = _seed_campaigns(names=[campaign_name])[0]
    now = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
    report = tmp_path / "browser table.csv"
    _write_report(
        report,
        _report(customer_id="123-456-7890", campaign_name=campaign_name),
        now,
    )

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        campaign = db.get(Campaign, campaign_id)
        spend = db.scalar(select(Spend))
        stats = db.scalar(select(CampaignDailyStat))

    item = result["file_results"][0]
    assert result["status"] == "SUCCESS"
    assert result["files_content_detected"] == 1
    assert result["rows_written"] == 1
    assert item["detection_method"] == "CONTENT_SIGNATURE"
    assert item["account_identity"]["status"] == "VERIFIED_CUSTOMER_ID"
    assert item["campaign_id_resolution"] == {
        "method": "EXACT_CUSTOMER_AND_CAMPAIGN_NAME",
        "attempted_rows": 1,
        "resolved_rows": 1,
        "unresolved_rows": 0,
    }
    assert campaign is not None
    assert campaign.external_id == "24116162130"
    assert campaign.status == "PAUSED"
    assert campaign.daily_budget == Decimal("1300000")
    assert campaign.currency == "VND"
    assert spend is not None and spend.currency == "VND"
    assert stats is not None and stats.clicks == 447


def test_wrong_customer_id_is_blocked_before_name_recovery_write(
    tmp_path: Path,
) -> None:
    campaign_name = "fliki.ai 10/8/2026 - 50$"
    _seed_campaigns(names=[campaign_name])
    now = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
    report = tmp_path / "browser table.csv"
    _write_report(
        report,
        _report(customer_id="785-917-3625", campaign_name=campaign_name),
        now,
    )

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        account_count = db.scalar(select(func.count()).select_from(AdsAccount))
        spend_count = db.scalar(select(func.count()).select_from(Spend))

    item = result["file_results"][0]
    assert result["status"] == "PARTIAL"
    assert result["files_account_mismatch"] == 1
    assert result["rows_written"] == 0
    assert item["status"] == "ACCOUNT_MISMATCH"
    assert item["account_identity"]["status"] == "CUSTOMER_ID_MISMATCH"
    assert item["campaign_id_resolution"]["resolved_rows"] == 0
    assert account_count == 1
    assert spend_count == 0


def test_duplicate_campaign_names_are_never_guessed(tmp_path: Path) -> None:
    campaign_name = "same campaign name"
    _seed_campaigns(names=[campaign_name, campaign_name])
    now = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
    report = tmp_path / "browser table.csv"
    _write_report(
        report,
        _report(customer_id="123-456-7890", campaign_name=campaign_name),
        now,
    )

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        spend_count = db.scalar(select(func.count()).select_from(Spend))

    item = result["file_results"][0]
    assert result["status"] == "PARTIAL"
    assert result["rows_written"] == 0
    assert item["status"] == "ERROR"
    assert item["campaign_id_resolution"]["unresolved_rows"] == 1
    assert "khớp nhiều campaign" in item["error"]
    assert spend_count == 0


def test_unknown_campaign_name_requires_real_campaign_id(tmp_path: Path) -> None:
    _seed_campaigns(names=["known campaign"])
    now = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
    report = tmp_path / "browser table.csv"
    _write_report(
        report,
        _report(customer_id="123-456-7890", campaign_name="unknown campaign"),
        now,
    )

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        spend_count = db.scalar(select(func.count()).select_from(Spend))

    item = result["file_results"][0]
    assert result["status"] == "PARTIAL"
    assert item["status"] == "ERROR"
    assert "không khớp campaign đã lưu" in item["error"]
    assert spend_count == 0


def test_blank_customer_id_cannot_use_fallback_for_id_recovery(
    tmp_path: Path,
) -> None:
    campaign_name = "fliki.ai 10/8/2026 - 50$"
    _seed_campaigns(names=[campaign_name])
    now = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
    report = tmp_path / "browser table.csv"
    _write_report(
        report,
        _report(customer_id="", campaign_name=campaign_name),
        now,
    )

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        spend_count = db.scalar(select(func.count()).select_from(Spend))

    item = result["file_results"][0]
    assert result["status"] == "PARTIAL"
    assert result["files_account_mismatch"] == 1
    assert item["status"] == "ACCOUNT_MISMATCH"
    assert item["account_identity"]["status"] == "CUSTOMER_ID_VALUE_REQUIRED"
    assert item["campaign_id_resolution"]["resolved_rows"] == 0
    assert spend_count == 0
