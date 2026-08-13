from __future__ import annotations

import pytest
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import PermissionStatus
from afi_os.models import Campaign, CampaignProgramLink, Merchant, Program, Spend
from afi_os.services.campaign_import import (
    analyze_campaign_import,
    commit_campaign_import,
)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _report(campaign_name: str, *, campaign_id: str = "campaign-1") -> bytes:
    return (
        "Date,Campaign ID,Campaign,Campaign status,Campaign type,"
        "Currency code,Cost,Impressions,Clicks,Conversions\n"
        f"2026-08-10,{campaign_id},{campaign_name},ENABLED,SEARCH,"
        "USD,25.50,100,10,1\n"
    ).encode()


def _program(domain: str, name: str) -> int:
    with SessionLocal() as db:
        merchant = Merchant(name=name, website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name=f"{name} Affiliate")
        db.add(program)
        db.commit()
        return program.id


def _analyze(db, data: bytes, default_program_id: int | None = None):
    return analyze_campaign_import(
        db,
        data,
        "GOOGLE_ADS_CSV_AUTO",
        "123-456-7890",
        "Google Ads",
        default_program_id,
    )


def test_exact_domain_in_campaign_name_is_auto_mapped_without_opening_permissions() -> None:
    program_id = _program("fliki.ai", "Fliki")

    with SessionLocal() as db:
        analysis = _analyze(db, _report("fliki.ai search 1"))
        assert analysis["mapped_rows"] == 1
        assert analysis["unmapped_rows"] == 0
        assert analysis["auto_mapped_rows"] == 1
        assert commit_campaign_import(db, analysis, actor="auto-folder") == 1

    with SessionLocal() as db:
        campaign = db.scalar(select(Campaign))
        link = db.scalar(select(CampaignProgramLink))
        program = db.get(Program, program_id)
        assert campaign is not None and campaign.launch_gate_status == "WARNING_ONLY"
        assert link is not None and link.program_id == program_id
        assert link.link_source == "CAMPAIGN_NAME_DOMAIN"
        assert program is not None
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
        assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
        assert program.non_brand_permission == PermissionStatus.NOT_CHECKED
        assert program.direct_link_permission == PermissionStatus.NOT_CHECKED


def test_domain_substring_does_not_auto_map() -> None:
    _program("fliki.ai", "Fliki")

    with SessionLocal() as db:
        analysis = _analyze(db, _report("notfliki.ai search"))
        assert analysis["mapped_rows"] == 0
        assert analysis["unmapped_rows"] == 1
        assert analysis["auto_mapped_rows"] == 0
        commit_campaign_import(db, analysis)
        assert db.scalar(select(func.count()).select_from(CampaignProgramLink)) == 0


def test_ambiguous_programs_for_one_domain_stay_unmapped() -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Fliki", website_domain="fliki.ai")
        db.add(merchant)
        db.flush()
        db.add_all(
            [
                Program(merchant_id=merchant.id, name="Fliki Affiliate A"),
                Program(merchant_id=merchant.id, name="Fliki Affiliate B"),
            ]
        )
        db.commit()

    with SessionLocal() as db:
        analysis = _analyze(db, _report("fliki.ai search"))
        assert analysis["mapped_rows"] == 0
        assert analysis["unmapped_rows"] == 1
        assert analysis["auto_mapped_rows"] == 0
        commit_campaign_import(db, analysis)
        assert db.scalar(select(func.count()).select_from(CampaignProgramLink)) == 0


def test_campaign_name_auto_map_never_overrides_manual_mapping() -> None:
    manual_program_id = _program("fliki.ai", "Fliki")
    inferred_program_id = _program("pictory.ai", "Pictory")
    report = _report("pictory.ai search")

    with SessionLocal() as db:
        initial = _analyze(db, report, default_program_id=manual_program_id)
        commit_campaign_import(db, initial, link_source="MANUAL")

    with SessionLocal() as db:
        analysis = _analyze(db, report)
        assert analysis["duplicates_existing"] == 1
        assert analysis["auto_mapped_rows"] == 0
        assert commit_campaign_import(db, analysis) == 0
        link = db.scalar(select(CampaignProgramLink))
        assert link is not None and link.program_id == manual_program_id
        assert link.program_id != inferred_program_id
        assert link.link_source == "MANUAL"


def test_auto_mapping_is_idempotent() -> None:
    program_id = _program("fliki.ai", "Fliki")
    report = _report("fliki.ai search")

    with SessionLocal() as db:
        first = _analyze(db, report)
        assert commit_campaign_import(db, first) == 1

    with SessionLocal() as db:
        second = _analyze(db, report)
        assert second["duplicates_existing"] == 1
        assert second["auto_mapped_rows"] == 0
        assert commit_campaign_import(db, second) == 0
        link = db.scalar(select(CampaignProgramLink))
        assert link is not None and link.program_id == program_id
        assert db.scalar(select(func.count()).select_from(Spend)) == 1
