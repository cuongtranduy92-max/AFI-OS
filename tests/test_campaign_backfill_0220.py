from __future__ import annotations

import pytest
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import PermissionStatus
from afi_os.models import (
    AdsAccount,
    AuditLog,
    Campaign,
    CampaignProgramLink,
    Merchant,
    Program,
)
from afi_os.services.campaign_import import backfill_campaign_domain_mappings


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program(db, domain: str, name: str) -> Program:
    merchant = Merchant(name=name, website_domain=domain)
    db.add(merchant)
    db.flush()
    program = Program(merchant_id=merchant.id, name=f"{name} Affiliate")
    db.add(program)
    db.flush()
    return program


def _campaign(db, name: str, external_id: str) -> Campaign:
    account = db.scalar(select(AdsAccount))
    if account is None:
        account = AdsAccount(
            external_id="123-456-7890",
            name="Google Ads",
            currency="USD",
        )
        db.add(account)
        db.flush()
    campaign = Campaign(
        ads_account_id=account.id,
        external_id=external_id,
        name=name,
        status="ENABLED",
        channel_type="SEARCH",
        currency="USD",
        launch_gate_status="WARNING_ONLY",
    )
    db.add(campaign)
    db.flush()
    return campaign


def test_backfill_maps_existing_unlinked_campaign_without_changing_permissions() -> None:
    with SessionLocal() as db:
        program = _program(db, "fliki.ai", "Fliki")
        campaign = _campaign(db, "fliki.ai legacy search", "legacy-1")
        program_id = program.id
        campaign_id = campaign.id
        db.commit()

    with SessionLocal() as db:
        result = backfill_campaign_domain_mappings(db)
        link = db.scalar(select(CampaignProgramLink))
        program = db.get(Program, program_id)
        campaign = db.get(Campaign, campaign_id)
        assert result == {
            "campaigns_total": 1,
            "unlinked_scanned": 1,
            "mapped": 1,
            "unresolved": 0,
            "preserved_existing": 0,
        }
        assert link is not None and link.program_id == program_id
        assert link.link_source == "CAMPAIGN_NAME_DOMAIN"
        assert campaign is not None and campaign.launch_gate_status == "WARNING_ONLY"
        assert program is not None
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
        assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_backfill_leaves_substrings_and_ambiguous_domains_unmapped() -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Fliki", website_domain="fliki.ai")
        db.add(merchant)
        db.flush()
        db.add_all(
            [
                Program(merchant_id=merchant.id, name="Fliki A"),
                Program(merchant_id=merchant.id, name="Fliki B"),
            ]
        )
        _campaign(db, "fliki.ai ambiguous", "ambiguous")
        _campaign(db, "notfliki.ai substring", "substring")
        db.commit()

    with SessionLocal() as db:
        result = backfill_campaign_domain_mappings(db)
        assert result["mapped"] == 0
        assert result["unresolved"] == 2
        assert db.scalar(select(func.count()).select_from(CampaignProgramLink)) == 0


def test_backfill_preserves_manual_mapping_and_is_idempotent() -> None:
    with SessionLocal() as db:
        manual_program = _program(db, "fliki.ai", "Fliki")
        inferred_program = _program(db, "pictory.ai", "Pictory")
        campaign = _campaign(db, "pictory.ai search", "manual-1")
        db.add(
            CampaignProgramLink(
                campaign_id=campaign.id,
                program_id=manual_program.id,
                link_source="MANUAL",
            )
        )
        manual_program_id = manual_program.id
        inferred_program_id = inferred_program.id
        db.commit()

    with SessionLocal() as db:
        first = backfill_campaign_domain_mappings(db)
        second = backfill_campaign_domain_mappings(db)
        link = db.scalar(select(CampaignProgramLink))
        assert first["preserved_existing"] == 1
        assert first["mapped"] == 0
        assert second == first
        assert link is not None and link.program_id == manual_program_id
        assert link.program_id != inferred_program_id
        assert link.link_source == "MANUAL"
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
