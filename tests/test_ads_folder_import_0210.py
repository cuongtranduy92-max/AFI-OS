from __future__ import annotations

import hashlib
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import SyncStatus
from afi_os.models import (
    AdsAccount,
    AuditLog,
    Campaign,
    CampaignProgramLink,
    Merchant,
    Program,
    Spend,
    SyncRun,
)
from afi_os.services.ads_folder_import import (
    CONNECTOR,
    ads_report_intraday_refresh_due,
    ads_report_is_stale,
    discover_campaign_reports,
    import_downloaded_campaign_reports,
    latest_report_source_at,
)
from afi_os.services.google_ads_api_sync import CONNECTOR as API_CONNECTOR
from afi_os.services.operations import operations_inbox


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _report(*, include_campaign_id: bool = True, cost: str = "149291") -> str:
    suffix = ",ID Chiến Dịch" if include_campaign_id else ""
    row_suffix = ",24116162130" if include_campaign_id else ""
    return (
        "Báo cáo chiến dịch\n"
        '"1 tháng 8, 2026 - 10 tháng 8, 2026"\n'
        "Ngày,Trạng thái chiến dịch,Chiến dịch,Mã đơn vị tiền tệ,"
        "Loại chiến dịch,Lượt chuyển đổi,Số lượt hiển thị,Lượt nhấp,Chi phí"
        f"{suffix}\n"
        "2026-08-10,Đang bật,fliki.ai 10/8/2026 - 50$,VND,Tìm kiếm,"
        f"0,851,384,{cost}{row_suffix}\n"
    )


def _renamed_report_without_date(*, commission_marker: bool = False) -> str:
    marker = ",Commission" if commission_marker else ""
    marker_value = ",40" if commission_marker else ""
    return (
        "Campaign ID,Campaign,Campaign status,Campaign type,Currency code,"
        f"Cost,Impressions,Clicks,Conversions{marker}\n"
        "24116162130,fliki.ai 10/8/2026 - 50$,Enabled,Search,VND,"
        f"149291,851,384,0{marker_value}\n"
    )


def _browser_report(
    *,
    customer_id: str | None = None,
    currency: str = "USD",
    campaign_id: str = "24126885583",
    campaign_name: str = "mubert - 10/8/2026 - 50$",
    campaign_state: str = "Enabled",
) -> str:
    customer_header = ",Customer ID" if customer_id is not None else ""
    customer_value = f",{customer_id}" if customer_id is not None else ""
    return (
        "Untitled report\n"
        '"July 14, 2026 - August 10, 2026"\n'
        "Campaign state,Campaign,Currency code,Budget,Campaign status,"
        "Campaign type,Day,Campaign ID,Impr.,Cost,Clicks,Conversions"
        f"{customer_header}\n"
        f"{campaign_state},{campaign_name},{currency},50.00,Eligible,Search,"
        f"2026-08-10,{campaign_id},151,16.29,71,0{customer_value}\n"
    )


def _seed_linked_campaign() -> tuple[int, int]:
    with SessionLocal() as db:
        merchant = Merchant(name="Fliki", website_domain="fliki.ai")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Fliki Affiliate")
        account = AdsAccount(
            external_id="123-456-7890",
            name="Google Ads",
            currency="VND",
        )
        db.add_all([program, account])
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            external_id="24116162130",
            name="fliki.ai 10/8/2026 - 50$",
            status="ENABLED",
            channel_type="SEARCH",
            currency="VND",
        )
        db.add(campaign)
        db.flush()
        db.add(
            CampaignProgramLink(
                campaign_id=campaign.id,
                program_id=program.id,
                link_source="MANUAL",
            )
        )
        db.commit()
        return program.id, campaign.id


def test_discovery_uses_only_newest_stable_report_in_each_family(tmp_path: Path) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    old = tmp_path / "Báo cáo chiến dịch.csv"
    newest = tmp_path / "Báo cáo chiến dịch (1).csv"
    unrelated = tmp_path / "commissions.csv"
    old.write_text(_report(include_campaign_id=False), encoding="utf-8")
    newest.write_text(_report(), encoding="utf-8")
    unrelated.write_text("amount\n10\n", encoding="utf-8")
    os.utime(old, (now.timestamp() - 600, now.timestamp() - 600))
    os.utime(newest, (now.timestamp() - 300, now.timestamp() - 300))
    os.utime(unrelated, (now.timestamp() - 300, now.timestamp() - 300))

    discovered = discover_campaign_reports(tmp_path, now=now)
    assert discovered == [newest]


def test_discovery_recognizes_renamed_report_and_rejects_commission_like_csv(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    older = tmp_path / "export from browser.csv"
    newest = tmp_path / "my renamed data.csv"
    commission_like = tmp_path / "affiliate payouts.csv"
    older.write_text(_report(), encoding="utf-8")
    newest.write_text(_report(cost="250000"), encoding="utf-8")
    commission_like.write_text(
        "Campaign ID,Campaign,Date,Amount,Impressions,Commission\n"
        "24116162130,fliki.ai,2026-08-10,100,12,40\n",
        encoding="utf-8",
    )
    os.utime(older, (now.timestamp() - 600, now.timestamp() - 600))
    os.utime(newest, (now.timestamp() - 300, now.timestamp() - 300))
    os.utime(
        commission_like,
        (now.timestamp() - 120, now.timestamp() - 120),
    )

    assert discover_campaign_reports(tmp_path, now=now) == [newest]


def test_auto_import_is_idempotent_and_keeps_existing_program_mapping(
    tmp_path: Path,
) -> None:
    program_id, campaign_id = _seed_linked_campaign()
    report = tmp_path / "Báo cáo chiến dịch (1).csv"
    report.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
    assert first["status"] == "SUCCESS"
    assert first["rows_written"] == 1
    assert first["cache_version"] == 9
    assert first["files_content_detected"] == 0
    assert first["file_results"][0]["detection_method"] == "FILENAME"
    assert first["file_results"][0]["mapped_rows"] == 1
    assert first["file_results"][0]["unmapped_rows"] == 0
    assert first["file_results"][0]["metric_date_from"] == "2026-08-10"
    assert first["file_results"][0]["metric_date_to"] == "2026-08-10"

    with SessionLocal() as db:
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=6),
            min_age_seconds=0,
        )
        assert second["files_unchanged"] == 1
        assert second["rows_written"] == 0
        assert db.scalar(select(func.count()).select_from(Spend)) == 1
        link = db.scalar(
            select(CampaignProgramLink).where(
                CampaignProgramLink.campaign_id == campaign_id
            )
        )
        assert link is not None and link.program_id == program_id
        program = db.get(Program, program_id)
        assert program.paid_search_permission.value == "NOT_CHECKED"
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.entity_type == "campaign_import")
            .order_by(AuditLog.id.desc())
        )
        assert audit is not None and audit.actor == "auto-folder"
        assert db.scalar(
            select(func.count()).select_from(SyncRun).where(SyncRun.connector == CONNECTOR)
        ) == 2


def test_auto_import_accepts_renamed_report_without_opening_ppc_permission(
    tmp_path: Path,
) -> None:
    program_id, _campaign_id = _seed_linked_campaign()
    report = tmp_path / "download renamed by operator.csv"
    report.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        program = db.get(Program, program_id)
        assert first["status"] == "SUCCESS"
        assert first["files_seen"] == 1
        assert first["files_content_detected"] == 1
        assert first["rows_written"] == 1
        assert first["file_results"][0]["detection_method"] == "CONTENT_SIGNATURE"
        assert program is not None
        assert program.paid_search_permission.value == "NOT_CHECKED"

    with SessionLocal() as db:
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=6),
            min_age_seconds=0,
        )
        assert second["files_content_detected"] == 1
        assert second["files_unchanged"] == 1
        assert second["rows_written"] == 0
        assert second["file_results"][0]["detection_method"] == "CONTENT_SIGNATURE"
        assert db.scalar(select(func.count()).select_from(Spend)) == 1


def test_browser_report_from_wrong_currency_account_is_blocked_before_write(
    tmp_path: Path,
) -> None:
    _seed_linked_campaign()
    report = tmp_path / "Untitled report.csv"
    report.write_text(_browser_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 12, 40, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db, today=now.date())
        account = db.scalar(select(AdsAccount))

        assert result["status"] == "PARTIAL"
        assert result["files_account_mismatch"] == 1
        assert result["rows_written"] == 0
        assert result["file_results"][0]["status"] == "ACCOUNT_MISMATCH"
        assert (
            result["file_results"][0]["account_identity"]["status"]
            == "ACCOUNT_CURRENCY_MISMATCH"
        )
        assert db.scalar(select(func.count()).select_from(Campaign)) == 1
        assert db.scalar(select(func.count()).select_from(Spend)) == 0
        assert account is not None and account.currency == "VND"
        item = next(
            item
            for item in inbox["items"]
            if item["item_type"] == "GOOGLE_ADS_ACCOUNT_MISMATCH"
        )
        assert item["requires_user"] is True
        assert "Đăng nhập đúng Customer ID 123-456-7890" in item["detail"]
        assert "File chưa được nhập" in item["detail"]


def test_explicit_wrong_customer_id_is_blocked_even_when_currency_matches(
    tmp_path: Path,
) -> None:
    _seed_linked_campaign()
    report = tmp_path / "browser export.csv"
    report.write_text(
        _browser_report(customer_id="785-917-3625", currency="VND"),
        encoding="utf-8",
    )
    now = datetime(2026, 8, 11, 12, 40, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        identity = result["file_results"][0]["account_identity"]
        assert result["files_account_mismatch"] == 1
        assert identity["status"] == "CUSTOMER_ID_MISMATCH"
        assert identity["expected_customer_ids"] == ["123-456-7890"]
        assert identity["reported_customer_ids"] == ["785-917-3625"]
        assert db.scalar(select(func.count()).select_from(AdsAccount)) == 1
        assert db.scalar(select(func.count()).select_from(Spend)) == 0


def test_blank_customer_id_cells_cannot_be_marked_as_verified(
    tmp_path: Path,
) -> None:
    _seed_linked_campaign()
    report = tmp_path / "browser export.csv"
    report.write_text(
        _browser_report(customer_id="", currency="VND"),
        encoding="utf-8",
    )
    now = datetime(2026, 8, 11, 12, 40, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        identity = result["file_results"][0]["account_identity"]
        inbox = operations_inbox(db, today=now.date())

        assert result["status"] == "PARTIAL"
        assert result["files_account_mismatch"] == 1
        assert result["rows_written"] == 0
        assert identity["status"] == "CUSTOMER_ID_VALUE_REQUIRED"
        assert identity["explicit_customer_id_rows"] == 0
        assert identity["fallback_customer_id_rows"] == 1
        assert identity["reported_customer_ids"] == ["123-456-7890"]
        assert db.scalar(select(func.count()).select_from(Campaign)) == 1
        assert db.scalar(select(func.count()).select_from(Spend)) == 0
        item = next(
            item
            for item in inbox["items"]
            if item["item_type"] == "GOOGLE_ADS_ACCOUNT_MISMATCH"
        )
        assert "cột Customer ID" in item["detail"]
        assert "1 dòng để trống" in item["detail"]
        assert "Đăng nhập đúng Customer ID 123-456-7890" in item["detail"]


def test_blank_customer_id_in_duplicate_row_cannot_hide_behind_dedupe(
    tmp_path: Path,
) -> None:
    _seed_linked_campaign()
    campaign_name = "fliki.ai duplicate-id gate"
    report_text = _browser_report(
        customer_id="1234567890",
        currency="VND",
        campaign_id="24128888888",
        campaign_name=campaign_name,
    )
    report_text += (
        f"Enabled,{campaign_name},VND,50.00,Eligible,Search,2026-08-10,"
        "24128888888,151,16.29,71,0,\n"
    )
    report = tmp_path / "browser export.csv"
    report.write_text(report_text, encoding="utf-8")
    now = datetime(2026, 8, 11, 12, 40, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        identity = result["file_results"][0]["account_identity"]

        assert result["status"] == "PARTIAL"
        assert result["files_account_mismatch"] == 1
        assert result["rows_written"] == 0
        assert identity["status"] == "CUSTOMER_ID_VALUE_REQUIRED"
        assert identity["explicit_customer_id_rows"] == 1
        assert identity["fallback_customer_id_rows"] == 1
        assert db.scalar(select(func.count()).select_from(Campaign)) == 1
        assert db.scalar(select(func.count()).select_from(Spend)) == 0


def test_explicit_target_customer_id_imports_and_campaign_state_wins(
    tmp_path: Path,
) -> None:
    _seed_linked_campaign()
    report = tmp_path / "browser export.csv"
    report.write_text(
        _browser_report(
            customer_id="1234567890",
            currency="VND",
            campaign_id="24199999999",
            campaign_name="fliki.ai browser campaign",
            campaign_state="Paused",
        ),
        encoding="utf-8",
    )
    now = datetime(2026, 8, 11, 12, 40, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        campaign = db.scalar(
            select(Campaign).where(Campaign.external_id == "24199999999")
        )
        identity = result["file_results"][0]["account_identity"]

        assert result["status"] == "SUCCESS"
        assert result["files_account_mismatch"] == 0
        assert result["rows_written"] == 1
        assert identity["status"] == "VERIFIED_CUSTOMER_ID"
        assert identity["reported_customer_ids"] == ["123-456-7890"]
        assert identity["explicit_customer_id_rows"] == 1
        assert identity["fallback_customer_id_rows"] == 0
        assert db.scalar(select(func.count()).select_from(AdsAccount)) == 1
        assert campaign is not None and campaign.status == "PAUSED"


def test_newer_renamed_near_match_reports_missing_date_and_exact_export_route(
    tmp_path: Path,
) -> None:
    program_id, _campaign_id = _seed_linked_campaign()
    valid = tmp_path / "Báo cáo chiến dịch.csv"
    missing_date = tmp_path / "latest export renamed.csv"
    valid.write_text(_report(), encoding="utf-8")
    missing_date.write_text(_renamed_report_without_date(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(valid, (now.timestamp() - 600, now.timestamp() - 600))
    os.utime(missing_date, (now.timestamp() - 300, now.timestamp() - 300))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db, today=date(2026, 8, 12))
        program = db.get(Program, program_id)

    assert result["status"] == "SUCCESS"
    assert result["files_seen"] == 1
    assert result["files_missing_columns"] == 1
    assert result["rejected_candidates"][0]["missing_fields"] == ["metric_date"]
    assert result["rejected_candidates"][0]["missing_columns"] == ["Date / Ngày"]
    types = {item["item_type"] for item in inbox["items"]}
    assert "GOOGLE_ADS_REPORT_MISSING_COLUMNS" in types
    item = next(
        item
        for item in inbox["items"]
        if item["item_type"] == "GOOGLE_ADS_REPORT_MISSING_COLUMNS"
    )
    assert item["requires_user"] is True
    assert "Phân đoạn → Thời gian → Ngày" in item["detail"]
    assert "Downloads" in item["detail"]
    assert "GOOGLE_ADS_REPORT_STALE" not in types
    assert program is not None
    assert {
        program.paid_search_permission.value,
        program.brand_keyword_permission.value,
        program.non_brand_permission.value,
        program.direct_link_permission.value,
    } == {"NOT_CHECKED"}

    missing_date.write_text(_report(cost="250000"), encoding="utf-8")
    os.utime(missing_date, (now.timestamp() - 100, now.timestamp() - 100))
    with SessionLocal() as db:
        corrected = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=1),
            min_age_seconds=0,
        )
        corrected_inbox = operations_inbox(db, today=date(2026, 8, 12))
    assert corrected["files_missing_columns"] == 0
    assert all(
        item["item_type"] != "GOOGLE_ADS_REPORT_MISSING_COLUMNS"
        for item in corrected_inbox["items"]
    )


def test_commission_markers_block_renamed_near_match_warning(tmp_path: Path) -> None:
    report = tmp_path / "affiliate campaign earnings.csv"
    report.write_text(
        _renamed_report_without_date(commission_marker=True),
        encoding="utf-8",
    )
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 300, now.timestamp() - 300))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db, today=now.date())

    assert result["files_seen"] == 0
    assert result["files_missing_columns"] == 0
    assert result["rejected_candidates"] == []
    assert inbox["items"] == []


def test_renamed_near_match_missing_campaign_id_points_to_columns_menu(
    tmp_path: Path,
) -> None:
    report = tmp_path / "renamed missing id.csv"
    report.write_text(
        "Date,Campaign,Campaign status,Campaign type,Currency code,"
        "Cost,Impressions,Clicks,Conversions\n"
        "2026-08-10,fliki.ai,Enabled,Search,VND,149291,851,384,0\n",
        encoding="utf-8",
    )
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 300, now.timestamp() - 300))

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db, today=now.date())

    assert result["files_missing_columns"] == 1
    assert result["rejected_candidates"][0]["missing_fields"] == [
        "campaign_external_id"
    ]
    item = next(
        item
        for item in inbox["items"]
        if item["item_type"] == "GOOGLE_ADS_REPORT_MISSING_COLUMNS"
    )
    assert "Campaign ID" in item["detail"]
    assert "Cột → Thuộc tính → ID chiến dịch" in item["detail"]


def test_same_run_duplicate_checksum_is_parsed_once_and_prefers_known_filename(
    tmp_path: Path,
) -> None:
    program_id, _campaign_id = _seed_linked_campaign()
    known = tmp_path / "Báo cáo chiến dịch.csv"
    renamed = tmp_path / "operator duplicate.csv"
    known.write_text(_report(), encoding="utf-8")
    renamed.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(known, (now.timestamp() - 300, now.timestamp() - 300))
    os.utime(renamed, (now.timestamp() - 200, now.timestamp() - 200))

    with SessionLocal() as db:
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        program = db.get(Program, program_id)
        assert first["files_seen"] == 2
        assert first["files_processed"] == 1
        assert first["files_duplicate_skipped"] == 1
        assert first["rows_read"] == 1
        assert first["rows_written"] == 1
        duplicate = next(
            item
            for item in first["file_results"]
            if item["status"] == "DUPLICATE_SKIPPED"
        )
        assert duplicate["filename"] == renamed.name
        assert duplicate["duplicate_of"] == known.name
        assert db.scalar(select(func.count()).select_from(Spend)) == 1
        assert program is not None
        assert {
            program.paid_search_permission.value,
            program.brand_keyword_permission.value,
            program.non_brand_permission.value,
            program.direct_link_permission.value,
        } == {"NOT_CHECKED"}

    with SessionLocal() as db:
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=1),
            min_age_seconds=0,
        )
        assert second["files_unchanged"] == 1
        assert second["files_duplicate_skipped"] == 1
        assert second["files_processed"] == 0
        assert db.scalar(select(func.count()).select_from(Spend)) == 1


def test_newest_cross_family_snapshot_wins_and_old_snapshot_cannot_overwrite(
    tmp_path: Path,
) -> None:
    program_id, campaign_id = _seed_linked_campaign()
    known = tmp_path / "Báo cáo chiến dịch.csv"
    renamed = tmp_path / "latest browser export.csv"
    known.write_text(_report(cost="100"), encoding="utf-8")
    renamed.write_text(_report(cost="200"), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(known, (now.timestamp() - 300, now.timestamp() - 300))
    os.utime(renamed, (now.timestamp() - 200, now.timestamp() - 200))

    with SessionLocal() as db:
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        spend = db.scalar(select(Spend).where(Spend.campaign_id == campaign_id))
        program = db.get(Program, program_id)
        assert first["files_seen"] == 2
        assert first["files_superseded"] == 0
        assert first["confirmed_file_count"] == 2
        assert first["confirmed_rows_read"] == 1
        assert spend is not None and spend.amount == 200
        assert program is not None
        assert {
            program.paid_search_permission.value,
            program.brand_keyword_permission.value,
            program.non_brand_permission.value,
            program.direct_link_permission.value,
        } == {"NOT_CHECKED"}

    renamed.unlink()
    known.write_text(_report(cost="50"), encoding="utf-8")
    os.utime(known, (now.timestamp() - 400, now.timestamp() - 400))
    with SessionLocal() as db:
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=1),
            min_age_seconds=0,
        )
        spend = db.scalar(select(Spend).where(Spend.campaign_id == campaign_id))
        assert second["files_seen"] == 1
        assert second["files_superseded"] == 1
        assert second["file_results"][0]["status"] == "SUPERSEDED"
        assert second["rows_written"] == 0
        assert second["confirmed_rows_read"] == 1
        assert spend is not None and spend.amount == 200


def test_last_confirmation_survives_rejected_and_empty_scans_then_reuses_hash(
    tmp_path: Path,
) -> None:
    program_id, _campaign_id = _seed_linked_campaign()
    valid = tmp_path / "Báo cáo chiến dịch.csv"
    valid.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(valid, (now.timestamp() - 300, now.timestamp() - 300))

    with SessionLocal() as db:
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
    assert first["confirmed_file_count"] == 1
    assert first["confirmed_file_results"][0]["metric_date_to"] == "2026-08-10"
    assert first["last_confirmed_at"] == now.isoformat()

    valid.unlink()
    rejected = tmp_path / "renamed missing date.csv"
    rejected.write_text(_renamed_report_without_date(), encoding="utf-8")
    os.utime(rejected, (now.timestamp() + 60, now.timestamp() + 60))
    with SessionLocal() as db:
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(minutes=2),
            min_age_seconds=0,
        )
        rejected_inbox = operations_inbox(db, today=date(2026, 8, 12))
    assert second["files_seen"] == 0
    assert second["files_missing_columns"] == 1
    assert second["file_results"] == []
    assert second["confirmed_file_count"] == 1
    assert second["confirmed_file_results"][0]["metric_date_to"] == "2026-08-10"
    assert second["last_confirmed_at"] == now.isoformat()
    rejected_types = {item["item_type"] for item in rejected_inbox["items"]}
    assert "GOOGLE_ADS_REPORT_MISSING_COLUMNS" in rejected_types
    assert "GOOGLE_ADS_REPORT_STALE" not in rejected_types

    rejected.unlink()
    with SessionLocal() as db:
        third = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(minutes=4),
            min_age_seconds=0,
        )
        empty_inbox = operations_inbox(db, today=date(2026, 8, 12))
    assert third["files_seen"] == 0
    assert third["files_missing_columns"] == 0
    assert third["confirmed_file_count"] == 1
    assert third["last_confirmed_at"] == now.isoformat()
    empty_types = {item["item_type"] for item in empty_inbox["items"]}
    assert "GOOGLE_ADS_REPORT_STALE" in empty_types

    valid.write_text(_report(), encoding="utf-8")
    os.utime(valid, (now.timestamp() + 300, now.timestamp() + 300))
    with SessionLocal() as db:
        fourth = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(minutes=6),
            min_age_seconds=0,
        )
        program = db.get(Program, program_id)
        assert fourth["files_unchanged"] == 1
        assert fourth["files_processed"] == 0
        assert fourth["rows_written"] == 0
        assert fourth["last_confirmed_at"] == (
            now + timedelta(minutes=6)
        ).isoformat()
        assert db.scalar(select(func.count()).select_from(Spend)) == 1
        assert db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type == "campaign_import")
        ) == 1
        assert program is not None
        assert {
            program.paid_search_permission.value,
            program.brand_keyword_permission.value,
            program.non_brand_permission.value,
            program.direct_link_permission.value,
        } == {"NOT_CHECKED"}


def test_first_new_cache_scan_recovers_confirmation_across_legacy_empty_run(
    tmp_path: Path,
) -> None:
    older = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector=CONNECTOR,
                    started_at=older,
                    ended_at=older,
                    status=SyncStatus.SUCCESS,
                    rows_read=9,
                    rows_written=0,
                    metadata_json={
                        "cache_version": 6,
                        "file_results": [
                            {
                                "filename": "Báo cáo chiến dịch.csv",
                                "sha256": "a" * 64,
                                "status": "UP_TO_DATE",
                                "checked_at": older.isoformat(),
                                "rows_read": 9,
                                "metric_date_to": "2026-08-10",
                            }
                        ],
                    },
                ),
                SyncRun(
                    connector=CONNECTOR,
                    started_at=older + timedelta(hours=1),
                    ended_at=older + timedelta(hours=1),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={"cache_version": 6, "file_results": []},
                ),
            ]
        )
        db.commit()
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=older + timedelta(hours=2),
            min_age_seconds=0,
        )

    assert result["cache_version"] == 9
    assert result["files_seen"] == 0
    assert result["confirmed_file_count"] == 1
    assert result["confirmed_file_results"][0]["sha256"] == "a" * 64
    assert result["last_confirmed_at"] == older.isoformat()


def test_cache_upgrade_replaces_legacy_confirmation_with_snapshot_scopes(
    tmp_path: Path,
) -> None:
    _seed_linked_campaign()
    report = tmp_path / "Báo cáo chiến dịch.csv"
    report_text = _report()
    report.write_text(report_text, encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    modified_at = now - timedelta(hours=2)
    os.utime(report, (modified_at.timestamp(), modified_at.timestamp()))
    digest = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector=CONNECTOR,
                started_at=now - timedelta(minutes=5),
                ended_at=now - timedelta(minutes=4),
                status=SyncStatus.SUCCESS,
                rows_read=1,
                rows_written=0,
                metadata_json={
                    "cache_version": 7,
                    "confirmed_file_results": [
                        {
                            "filename": report.name,
                            "report_family": "bao_cao_chien_dich",
                            "sha256": digest,
                            "status": "UP_TO_DATE",
                            "checked_at": (now - timedelta(minutes=4)).isoformat(),
                            "rows_read": 1,
                            "metric_date_to": "2026-08-10",
                        }
                    ],
                },
            )
        )
        db.commit()
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )

    assert result["confirmed_rows_read"] == 1
    confirmed = result["confirmed_file_results"][0]
    assert confirmed["source_modified_at"] == modified_at.isoformat()
    assert confirmed["snapshot_scopes"] == [
        {
            "account_external_id": "123-456-7890",
            "metric_date": "2026-08-10",
            "rows": 1,
        }
    ]


def test_successful_unmapped_file_retries_after_program_domain_is_created(
    tmp_path: Path,
) -> None:
    report = tmp_path / "Báo cáo chiến dịch.csv"
    report.write_text(
        "Ngày,Trạng thái chiến dịch,Chiến dịch,Mã đơn vị tiền tệ,"
        "Loại chiến dịch,Lượt chuyển đổi,Số lượt hiển thị,Lượt nhấp,Chi phí,"
        "ID Chiến Dịch,program_domain\n"
        "2026-08-10,Đang bật,Generic campaign,VND,Tìm kiếm,0,100,10,50000,"
        "future-1,future.example\n",
        encoding="utf-8",
    )
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))
    with SessionLocal() as db:
        db.add(
            AdsAccount(
                external_id="123-456-7890",
                name="Google Ads",
                currency="VND",
            )
        )
        db.commit()
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
        assert first["status"] == "SUCCESS"
        assert first["file_results"][0]["unmapped_rows"] == 1
        assert first["files_retried_after_mapping"] == 0
        assert db.scalar(select(func.count()).select_from(CampaignProgramLink)) == 0
        assert db.scalar(select(func.count()).select_from(Spend)) == 1

    with SessionLocal() as db:
        merchant = Merchant(name="Future", website_domain="future.example")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Future Affiliate")
        db.add(program)
        db.commit()
        program_id = program.id
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=6),
            min_age_seconds=0,
        )
        link = db.scalar(select(CampaignProgramLink))
        assert second["status"] == "SUCCESS"
        assert second["files_unchanged"] == 0
        assert second["files_retried_after_mapping"] == 1
        assert second["file_results"][0]["mapped_rows"] == 1
        assert second["file_results"][0]["unmapped_rows"] == 0
        assert second["file_results"][0]["retried_after_mapping"] is True
        assert link is not None and link.program_id == program_id
        assert db.scalar(select(func.count()).select_from(Spend)) == 1
        assert program.paid_search_permission.value == "NOT_CHECKED"

        third = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=12),
            min_age_seconds=0,
        )
        assert third["files_unchanged"] == 1
        assert third["rows_written"] == 0
        assert db.scalar(select(func.count()).select_from(Spend)) == 1


def test_unchanged_error_is_retried_after_customer_context_becomes_available(
    tmp_path: Path,
) -> None:
    report = tmp_path / "Báo cáo chiến dịch.csv"
    report.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        first = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
    assert first["status"] == "PARTIAL"
    assert first["error_count"] == 1
    assert first["files_retried_after_error"] == 0
    assert "Thiếu Customer ID" in first["file_results"][0]["error"]

    with SessionLocal() as db:
        db.add(
            AdsAccount(
                external_id="123-456-7890",
                name="Google Ads",
                currency="VND",
            )
        )
        db.commit()
        second = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=6),
            min_age_seconds=0,
        )
        assert second["status"] == "SUCCESS"
        assert second["error_count"] == 0
        assert second["files_unchanged"] == 0
        assert second["files_retried_after_error"] == 1
        assert second["rows_read"] == 1
        assert second["rows_written"] == 1
        assert second["file_results"][0]["retried_after_error"] is True
        assert db.scalar(select(func.count()).select_from(Campaign)) == 1
        assert db.scalar(select(func.count()).select_from(Spend)) == 1


def test_import_error_and_unmapped_campaign_enter_operations_inbox(
    tmp_path: Path,
) -> None:
    report = tmp_path / "Báo cáo chiến dịch.csv"
    report.write_text(_report(include_campaign_id=False), encoding="utf-8")
    with SessionLocal() as db:
        account = AdsAccount(
            external_id="123-456-7890",
            name="Google Ads",
            currency="VND",
        )
        db.add(account)
        db.flush()
        db.add(
            Campaign(
                ads_account_id=account.id,
                external_id="unmapped-1",
                name="New unmapped campaign",
                status="ENABLED",
                channel_type="SEARCH",
                currency="VND",
            )
        )
        db.commit()

    with SessionLocal() as db:
        result = import_downloaded_campaign_reports(
            db,
            root=tmp_path,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db)

    assert result["status"] == "PARTIAL"
    assert result["error_count"] == 1
    types = {item["item_type"] for item in inbox["items"]}
    assert "GOOGLE_ADS_IMPORT_ERROR" in types
    assert "CAMPAIGN_PROGRAM_REQUIRED" in types
    assert all(item["action_view"] == "exposure" for item in inbox["items"])


def test_report_freshness_uses_metric_date_not_scan_time() -> None:
    file_results = [{"status": "UP_TO_DATE", "metric_date_to": "2026-08-10"}]
    assert ads_report_is_stale(file_results, today=datetime(2026, 8, 11).date()) is False
    assert ads_report_is_stale(file_results, today=datetime(2026, 8, 12).date()) is True


def test_intraday_freshness_uses_latest_same_day_source_timestamp() -> None:
    now = datetime(2026, 8, 11, 15, 0, tzinfo=UTC)
    file_results = [
        {
            "status": "UP_TO_DATE",
            "metric_date_to": "2026-08-10",
            "source_modified_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "status": "IMPORTED",
            "metric_date_to": "2026-08-11",
            "source_modified_at": (now - timedelta(hours=7)).isoformat(),
        },
        {
            "status": "UP_TO_DATE",
            "metric_date_to": "2026-08-11",
            "source_modified_at": (now - timedelta(hours=5)).isoformat(),
        },
    ]

    assert latest_report_source_at(file_results) == now - timedelta(hours=5)
    assert ads_report_intraday_refresh_due(file_results, now=now) is False

    file_results.pop()
    assert latest_report_source_at(file_results) == now - timedelta(hours=7)
    assert ads_report_intraday_refresh_due(file_results, now=now) is True

    file_results[1]["metric_date_to"] = "2026-08-10"
    assert ads_report_intraday_refresh_due(file_results, now=now) is False


def test_old_same_day_report_creates_warning_only_refresh_item() -> None:
    now = datetime(2026, 8, 11, 15, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector=CONNECTOR,
                started_at=now - timedelta(minutes=2),
                ended_at=now - timedelta(minutes=1),
                status=SyncStatus.SUCCESS,
                rows_read=0,
                rows_written=0,
                metadata_json={
                    "error_count": 0,
                    "confirmed_file_results": [
                        {
                            "filename": "google-ads-campaign-report.csv",
                            "sha256": "a" * 64,
                            "status": "UP_TO_DATE",
                            "metric_date_to": "2026-08-11",
                            "source_modified_at": (
                                now - timedelta(hours=7)
                            ).isoformat(),
                            "rows_read": 4,
                        }
                    ],
                },
            )
        )
        db.commit()
        inbox = operations_inbox(db, today=now.date(), now=now)

    refresh = [
        item
        for item in inbox["items"]
        if item["item_type"] == "GOOGLE_ADS_REPORT_INTRADAY_REFRESH"
    ]
    assert len(refresh) == 1
    assert refresh[0]["severity"] == "WARNING"
    assert refresh[0]["requires_user"] is False
    assert "không bị loại, sửa hoặc dừng" in refresh[0]["detail"]


def test_today_api_result_suppresses_intraday_csv_refresh_warning() -> None:
    now = datetime(2026, 8, 11, 15, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector=CONNECTOR,
                    started_at=now - timedelta(minutes=2),
                    ended_at=now - timedelta(minutes=1),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "error_count": 0,
                        "confirmed_file_results": [
                            {
                                "filename": "google-ads-campaign-report.csv",
                                "sha256": "a" * 64,
                                "status": "UP_TO_DATE",
                                "metric_date_to": "2026-08-11",
                                "source_modified_at": (
                                    now - timedelta(hours=7)
                                ).isoformat(),
                            }
                        ],
                    },
                ),
                SyncRun(
                    connector=API_CONNECTOR,
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=1,
                    rows_written=0,
                    metadata_json={"date_to": "2026-08-11"},
                ),
            ]
        )
        db.commit()
        inbox = operations_inbox(db, today=now.date(), now=now)

    assert all(
        item["item_type"] != "GOOGLE_ADS_REPORT_INTRADAY_REFRESH"
        for item in inbox["items"]
    )


def test_stale_report_creates_one_operator_action() -> None:
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector=CONNECTOR,
                started_at=datetime(2026, 8, 11, tzinfo=UTC),
                ended_at=datetime(2026, 8, 11, tzinfo=UTC),
                status=SyncStatus.SUCCESS,
                rows_read=0,
                rows_written=0,
                metadata_json={
                    "cache_version": 2,
                    "error_count": 0,
                    "file_results": [
                        {
                            "filename": "Báo cáo chiến dịch.csv",
                            "sha256": "a" * 64,
                            "status": "UP_TO_DATE",
                            "metric_date_to": "2026-08-09",
                        }
                    ],
                },
            )
        )
        db.commit()
        inbox = operations_inbox(db, today=datetime(2026, 8, 11).date())
    stale = [
        item for item in inbox["items"] if item["item_type"] == "GOOGLE_ADS_REPORT_STALE"
    ]
    assert len(stale) == 1
    assert stale[0]["requires_user"] is True
    assert "Google Ads" in stale[0]["detail"]
    assert "Downloads" in stale[0]["detail"]


def test_fresh_read_only_api_suppresses_csv_fallback_action() -> None:
    now = datetime(2026, 8, 11, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector=CONNECTOR,
                    started_at=now,
                    ended_at=now,
                    status=SyncStatus.PARTIAL,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "error_count": 1,
                        "files_missing_columns": 1,
                        "rejected_candidates": [
                            {
                                "filename": "renamed.csv",
                                "status": "MISSING_REQUIRED_COLUMNS",
                                "missing_fields": ["metric_date"],
                                "missing_columns": ["Date / Ngày"],
                            }
                        ],
                        "file_results": [
                            {
                                "filename": "Báo cáo chiến dịch.csv",
                                "status": "ERROR",
                                "error": "CSV cũ bị lỗi",
                                "metric_date_to": "2026-08-01",
                            }
                        ],
                    },
                ),
                SyncRun(
                    connector=API_CONNECTOR,
                    started_at=now,
                    ended_at=now,
                    status=SyncStatus.SUCCESS,
                    rows_read=9,
                    rows_written=0,
                    metadata_json={
                        "date_to": "2026-08-10",
                        "write_operations_enabled": False,
                    },
                ),
            ]
        )
        db.commit()
        inbox = operations_inbox(db, today=now.date())
    types = {item["item_type"] for item in inbox["items"]}
    assert "GOOGLE_ADS_REPORT_STALE" not in types
    assert "GOOGLE_ADS_IMPORT_ERROR" not in types
    assert "GOOGLE_ADS_REPORT_MISSING_COLUMNS" not in types
