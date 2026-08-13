from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    AuditAction,
    CommissionType,
    EvidenceReviewStatus,
    PermissionStatus,
    ResearchStatus,
    SourceAuthority,
)
from afi_os.main import app
from afi_os.models import AuditLog, CommissionFact, Program, TermsEvidence, TermsResearchRun

client = TestClient(app)
PERMISSION_FIELDS = (
    "paid_search_permission",
    "brand_keyword_permission",
    "non_brand_permission",
    "direct_link_permission",
    "trademark_in_ad_copy_permission",
)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_pictory_pack() -> int:
    response = client.post(
        "/api/programs",
        json={
            "merchant_name": "Pictory",
            "website_domain": "pictory.ai",
            "program_name": "Pictory Affiliate Program",
            "signup_url": "https://partners.pictory.ai/signup/40690",
        },
    )
    assert response.status_code == 200, response.text
    program_id = response.json()["id"]
    now = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    with SessionLocal() as db:
        evidence = TermsEvidence(
            program_id=program_id,
            source_url="https://pictory.ai/affiliate-terms",
            source_type="TERMS_PAGE",
            excerpt='=HYPERLINK("https://attacker.invalid","policy")',
            evidence_hash="e" * 64,
            checked_at=now,
            reviewer="automation",
            confidence=0.4,
            decision=PermissionStatus.NOT_CHECKED,
            scope="PAID_SEARCH",
            applies_to="PAID_SEARCH",
            review_status=EvidenceReviewStatus.PROPOSED,
            source_authority=SourceAuthority.OFFICIAL,
            collected_by="AUTOMATED_WEB",
        )
        facts = [
            CommissionFact(
                program_id=program_id,
                scope="COMMISSION",
                source_url="https://partners.pictory.ai/signup/40690",
                source_authority=SourceAuthority.OFFICIAL,
                excerpt="40% one-time commission on first payment.",
                checked_at=now,
                confidence=0.98,
                commission_type=CommissionType.ONE_TIME,
                commission_rate=Decimal("0.40"),
                rate_is_maximum=False,
                applies_to="FIRST_PAYMENT",
                review_status=EvidenceReviewStatus.PROPOSED,
                collected_by="AUTOMATED_WEB",
                evidence_hash="a" * 64,
            ),
            CommissionFact(
                program_id=program_id,
                scope="COMMISSION",
                source_url="https://pictory.ai/partners",
                source_authority=SourceAuthority.OFFICIAL,
                excerpt="Recurring commissions up to 50%.",
                checked_at=now,
                confidence=0.96,
                commission_type=CommissionType.RECURRING_LIFETIME,
                commission_rate=Decimal("0.50"),
                rate_is_maximum=True,
                applies_to="SUBSCRIPTION",
                review_status=EvidenceReviewStatus.PROPOSED,
                collected_by="AUTOMATED_WEB",
                evidence_hash="b" * 64,
            ),
        ]
        run = TermsResearchRun(
            program_id=program_id,
            domain="pictory.ai",
            fixture_version="test-v1",
            status=ResearchStatus.CONFLICT,
            checked_at=now,
            discovery_confidence=0.96,
            source_urls=[
                "https://partners.pictory.ai/signup/40690",
                "https://pictory.ai/partners",
            ],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="r" * 64,
            summary="Official commission sources conflict; PPC remains NOT_CHECKED.",
        )
        db.add_all([evidence, *facts, run])
        db.flush()
        db.add(
            AuditLog(
                entity_type="terms_research_run",
                entity_id=str(run.id),
                action=AuditAction.SYNC,
                actor="auto-maintenance",
                payload_json={
                    "duplicate_run": False,
                    "source_urls": run.source_urls,
                    "source_authorities": {
                        "https://partners.pictory.ai/signup/40690": "PARTNER_PORTAL",
                        "https://pictory.ai/partners": "OFFICIAL",
                    },
                    "source_snapshots": [
                        {
                            "url": "https://partners.pictory.ai/signup/40690",
                            "content_sha256": "1" * 64,
                            "source_authority": "PARTNER_PORTAL",
                        },
                        {
                            "url": "https://pictory.ai/partners",
                            "content_sha256": "2" * 64,
                            "source_authority": "OFFICIAL",
                        },
                    ],
                    "collection_errors": [],
                    "source_change_status": "UNCHANGED",
                    "source_changes": [],
                    "imported_terms_evidence": 1,
                    "imported_commission_facts": 2,
                    "permissions_changed": False,
                },
            )
        )
        db.add(
            AuditLog(
                entity_type="commission_fact",
                entity_id=str(facts[0].id),
                action=AuditAction.CREATE,
                actor="auto-maintenance",
                payload_json={
                    "program_id": program_id,
                    "commission_type": "ONE_TIME",
                    "commission_rate": "0.40",
                    "review_status": "PROPOSED",
                    "permissions_changed": False,
                    "unexported_internal_field": "must-not-leak",
                },
            )
        )
        db.commit()
    return program_id


def test_evidence_pack_separates_terms_commission_and_preserves_permissions() -> None:
    program_id = _seed_pictory_pack()
    with SessionLocal() as db:
        before = db.get(Program, program_id)
        assert before is not None
        permissions_before = {
            field: getattr(before, field).value for field in PERMISSION_FIELDS
        }
        audit_count_before = db.scalar(select(func.count()).select_from(AuditLog))

    response = client.get(f"/api/programs/{program_id}/evidence-pack")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-afi-os-permissions-changed"] == "false"
    assert "AFI-OS-evidence-pictory.ai-" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "commission-facts.csv",
            "manifest.json",
            "program-summary.json",
            "research-attempts.csv",
            "research-runs.csv",
            "review-audit.csv",
            "terms-evidence.csv",
        }
        summary = json.loads(archive.read("program-summary.json"))
        assert set(summary["canonical_permissions"].values()) == {"NOT_CHECKED"}
        assert summary["commission_state"] == "CONFLICT"
        assert summary["pack_format_version"] == 4
        assert summary["program"]["signup_url"] == (
            "https://partners.pictory.ai/signup/40690"
        )
        assert summary["program"]["signup_source_authority"] == "OFFICIAL"
        assert summary["collection"]["latest_source_authorities"] == {
            "https://partners.pictory.ai/signup/40690": "PARTNER_PORTAL",
            "https://pictory.ai/partners": "OFFICIAL",
        }
        assert summary["counts"] == {
            "commission_facts": 2,
            "research_attempts": 1,
            "research_runs": 1,
            "review_audit_events": 1,
            "source_urls": 3,
            "terms_evidence": 1,
        }
        assert summary["safety"] == {
            "commission_is_separate_from_ppc_permissions": True,
            "export_is_read_only": True,
            "permissions_changed_by_export": False,
            "projects_or_campaigns_excluded_by_export": False,
        }
        commission_rows = list(
            csv.DictReader(
                io.StringIO(archive.read("commission-facts.csv").decode("utf-8-sig"))
            )
        )
        assert {row["commission_type"] for row in commission_rows} == {
            "ONE_TIME",
            "RECURRING_LIFETIME",
        }
        assert {row["source_url"] for row in commission_rows} == {
            "https://partners.pictory.ai/signup/40690",
            "https://pictory.ai/partners",
        }
        evidence_row = next(
            csv.DictReader(
                io.StringIO(archive.read("terms-evidence.csv").decode("utf-8-sig"))
            )
        )
        assert evidence_row["scope"] == "PAID_SEARCH"
        assert evidence_row["decision"] == "NOT_CHECKED"
        assert evidence_row["review_status"] == "PROPOSED"
        assert evidence_row["checked_at"].startswith("2026-08-11T10:00:00")
        assert evidence_row["confidence"] == "0.4"
        assert evidence_row["excerpt"].startswith("'=HYPERLINK")
        attempt = next(
            csv.DictReader(
                io.StringIO(archive.read("research-attempts.csv").decode("utf-8-sig"))
            )
        )
        assert attempt["permissions_changed"] == "False"
        assert json.loads(attempt["source_authorities"]) == {
            "https://partners.pictory.ai/signup/40690": "PARTNER_PORTAL",
            "https://pictory.ai/partners": "OFFICIAL",
        }
        review_audit = next(
            csv.DictReader(
                io.StringIO(archive.read("review-audit.csv").decode("utf-8-sig"))
            )
        )
        assert review_audit["entity_type"] == "commission_fact"
        assert "permissions_changed" in review_audit["decision_metadata"]
        assert "unexported_internal_field" not in review_audit["decision_metadata"]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["pack_format_version"] == 4
        for item in manifest["files"]:
            payload = archive.read(item["path"])
            assert len(payload) == item["size_bytes"]
            assert hashlib.sha256(payload).hexdigest() == item["sha256"]
        assert "This export is read-only" in archive.read("README.txt").decode("utf-8")

    with SessionLocal() as db:
        after = db.get(Program, program_id)
        assert after is not None
        assert {
            field: getattr(after, field).value for field in PERMISSION_FIELDS
        } == permissions_before
        assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_count_before


def test_evidence_pack_unknown_program_returns_404() -> None:
    response = client.get("/api/programs/999/evidence-pack")
    assert response.status_code == 404


def test_evidence_pack_inventories_standalone_partner_signup_source() -> None:
    signup_url = "https://network.example.net/signup/merchant-1"
    created = client.post(
        "/api/programs",
        json={
            "merchant_name": "Standalone Merchant",
            "website_domain": "standalone.example",
            "program_name": "Standalone Affiliate Program",
            "signup_url": signup_url,
        },
    )
    assert created.status_code == 200, created.text

    response = client.get(
        f"/api/programs/{created.json()['id']}/evidence-pack"
    )
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        summary = json.loads(archive.read("program-summary.json"))
        assert summary["pack_format_version"] == 4
        assert summary["program"]["signup_url"] == signup_url
        assert summary["program"]["signup_source_authority"] == "PARTNER_PORTAL"
        assert summary["source_urls"] == [signup_url]
        assert summary["counts"] == {
            "commission_facts": 0,
            "research_attempts": 0,
            "research_runs": 0,
            "review_audit_events": 0,
            "source_urls": 1,
            "terms_evidence": 0,
        }
        assert set(summary["canonical_permissions"].values()) == {"NOT_CHECKED"}
        readme = archive.read("README.txt").decode("utf-8")
        assert f"URL: {signup_url}" in readme
        assert "Authority: PARTNER_PORTAL" in readme


def test_terms_ui_exposes_evidence_pack_download_for_selected_program() -> None:
    page = client.get("/")
    script = client.get("/app.js")
    assert page.status_code == 200
    assert 'id="exportEvidencePack"' in page.text
    assert "Xuất evidence pack" in page.text
    assert "/evidence-pack`" in script.text
    assert 'link.download = ""' in script.text
    assert 'data-evidence-pack-program="${esc(item.program_id)}"' in script.text
    assert ">Tải pack</button>" in script.text
    assert "setEvidenceProgramSelection(programId)" in script.text
