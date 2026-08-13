from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.models import Commission, Conversion, Merchant, Program
from afi_os.services.commission_folder_import import (
    discover_commission_reports,
    import_downloaded_commission_reports,
)
from afi_os.services.operations import operations_inbox


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_program(domain: str = "fliki.ai", name: str = "Fliki") -> int:
    with SessionLocal() as db:
        merchant = Merchant(name=name, website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(
            merchant_id=merchant.id,
            name=f"{name} Affiliate Program",
        )
        db.add(program)
        db.commit()
        return program.id


def _report(*, state: str = "pending", extra_header: str = "", extra: str = "") -> str:
    return (
        f"transaction_id,amount,currency,status,date{extra_header}\n"
        f"sale-1,12.50,USD,{state},2026-08-10{extra}\n"
    )


def test_discovery_selects_newest_stable_numbered_report(tmp_path: Path) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    older = tmp_path / "Fliki commissions.csv"
    newer = tmp_path / "Fliki commissions (1).csv"
    unrelated = tmp_path / "bank transactions.csv"
    for path in (older, newer, unrelated):
        path.write_text(_report(), encoding="utf-8")
    os.utime(older, (now.timestamp() - 600, now.timestamp() - 600))
    os.utime(newer, (now.timestamp() - 300, now.timestamp() - 300))
    os.utime(unrelated, (now.timestamp() - 300, now.timestamp() - 300))

    assert discover_commission_reports(tmp_path, now=now) == [newer]


def test_auto_import_is_idempotent_and_updates_state_with_stable_source(
    tmp_path: Path,
) -> None:
    program_id = _seed_program()
    report = tmp_path / "Fliki commissions (1).csv"
    report.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        first = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
    assert first["status"] == "SUCCESS"
    assert first["cache_version"] == 2
    assert first["rows_written"] == 1
    assert first["file_results"][0]["source"] == "AFFILIATE_FLIKI_AI"
    assert first["file_results"][0]["program_id"] == program_id

    with SessionLocal() as db:
        unchanged = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=6),
            min_age_seconds=0,
        )
        assert unchanged["files_unchanged"] == 1
        assert unchanged["rows_written"] == 0
        assert db.scalar(select(func.count()).select_from(Commission)) == 1

    report.write_text(_report(state="approved"), encoding="utf-8")
    changed_at = now + timedelta(hours=11)
    os.utime(report, (changed_at.timestamp(), changed_at.timestamp()))
    with SessionLocal() as db:
        updated = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=12),
            min_age_seconds=0,
        )
        commission = db.scalar(select(Commission))
        conversion = db.scalar(select(Conversion))
        program = db.get(Program, program_id)
    assert updated["rows_written"] == 1
    assert commission is not None and commission.state.value == "APPROVED"
    assert conversion is not None and conversion.program_id == program_id
    assert program is not None and program.paid_search_permission.value == "NOT_CHECKED"


def test_same_file_recovers_after_matching_program_is_created(tmp_path: Path) -> None:
    report = tmp_path / "Fliki commissions.csv"
    report.write_text(_report(), encoding="utf-8")
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    os.utime(report, (now.timestamp() - 60, now.timestamp() - 60))

    with SessionLocal() as db:
        first = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            now=now,
            min_age_seconds=0,
        )
    assert first["status"] == "PARTIAL"
    assert first["mapping_required_count"] == 1
    assert first["files_retried_after_mapping"] == 0
    assert first["file_results"][0]["status"] == "MAPPING_REQUIRED"

    program_id = _seed_program()
    with SessionLocal() as db:
        second = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            now=now + timedelta(hours=6),
            min_age_seconds=0,
        )
        commission = db.scalar(select(Commission))
        conversion = db.scalar(select(Conversion))
    assert second["status"] == "SUCCESS"
    assert second["files_unchanged"] == 0
    assert second["files_retried_after_mapping"] == 1
    assert second["rows_read"] == 1
    assert second["rows_written"] == 1
    assert second["file_results"][0]["retry_reason"] == "MAPPING_REQUIRED"
    assert commission is not None
    assert conversion is not None and conversion.program_id == program_id


def test_unmapped_file_enters_inbox_and_rename_reprocesses_same_content(
    tmp_path: Path,
) -> None:
    program_id = _seed_program()
    generic = tmp_path / "commissions.csv"
    generic.write_text(_report(), encoding="utf-8")

    with SessionLocal() as db:
        first = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db)
        assert db.scalar(select(func.count()).select_from(Commission)) == 0
    assert first["status"] == "PARTIAL"
    assert first["mapping_required_count"] == 1
    mapping = [
        item
        for item in inbox["items"]
        if item["item_type"] == "COMMISSION_FILE_MAPPING_REQUIRED"
    ]
    assert len(mapping) == 1
    assert mapping[0]["action_view"] == "finance"
    assert "program_domain" in mapping[0]["detail"]

    named = tmp_path / "Fliki commissions.csv"
    generic.rename(named)
    with SessionLocal() as db:
        second = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            min_age_seconds=0,
        )
        conversion = db.scalar(select(Conversion))
        second_inbox = operations_inbox(db)
    assert second["status"] == "SUCCESS"
    assert second["rows_written"] == 1
    assert conversion is not None and conversion.program_id == program_id
    assert not any(
        item["item_type"] == "COMMISSION_FILE_MAPPING_REQUIRED"
        for item in second_inbox["items"]
    )


def test_program_domain_column_maps_a_generic_report(tmp_path: Path) -> None:
    program_id = _seed_program()
    report = tmp_path / "commissions.csv"
    report.write_text(
        _report(extra_header=",program_domain", extra=",fliki.ai"),
        encoding="utf-8",
    )
    with SessionLocal() as db:
        result = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            min_age_seconds=0,
        )
        conversion = db.scalar(select(Conversion))
    assert result["rows_written"] == 1
    assert conversion is not None and conversion.program_id == program_id


def test_invalid_report_never_auto_commits_and_enters_inbox(tmp_path: Path) -> None:
    _seed_program()
    report = tmp_path / "Fliki commissions.csv"
    report.write_text("transaction_id,status\nsale-1,pending\n", encoding="utf-8")
    with SessionLocal() as db:
        result = import_downloaded_commission_reports(
            db,
            root=tmp_path,
            min_age_seconds=0,
        )
        inbox = operations_inbox(db)
        commission_count = db.scalar(select(func.count()).select_from(Commission))
    assert result["status"] == "PARTIAL"
    assert result["error_count"] == 1
    assert result["rows_written"] == 0
    assert commission_count == 0
    errors = [
        item
        for item in inbox["items"]
        if item["item_type"] == "COMMISSION_IMPORT_ERROR"
    ]
    assert len(errors) == 1
    assert "không bị thay đổi" in errors[0]["detail"]
