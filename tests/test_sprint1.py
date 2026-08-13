from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete

from afi_os.db import SessionLocal, engine
from afi_os.main import app
from afi_os.models import AffiliateNetwork, Commission, Conversion, Merchant, Program, TermsEvidence
from afi_os.services.backups import backup_root

client = TestClient(app)


def _clear_program_finance() -> None:
    with SessionLocal() as db:
        db.execute(delete(Commission))
        db.execute(delete(Conversion))
        db.execute(delete(TermsEvidence))
        db.execute(delete(Program))
        db.execute(delete(Merchant))
        db.execute(delete(AffiliateNetwork))
        db.commit()


def test_program_evidence_gate_and_deduplication() -> None:
    _clear_program_finance()
    created = client.post(
        "/api/programs",
        json={
            "merchant_name": "Example AI",
            "website_domain": "example.ai",
            "program_name": "Example Affiliate",
            "network_name": "Rewardful",
            "paid_search_permission": "NON_BRAND_ONLY",
            "brand_keyword_permission": "PROHIBITED",
            "non_brand_permission": "NON_BRAND_ONLY",
            "direct_link_permission": "NOT_CHECKED",
        },
    )
    assert created.status_code == 200, created.text
    program_id = created.json()["id"]
    assert created.json()["gate_status"] == "WARNING_TERMS_UNVERIFIED"

    checked = datetime.now(UTC).isoformat()
    paid_payload = {
        "source_url": "https://example.ai/terms",
        "excerpt": "Paid search is permitted except trademark terms.",
        "checked_at": checked,
        "reviewer": "Tran",
        "confidence": 1,
        "source_authority": "OFFICIAL",
        "decision": "NON_BRAND_ONLY",
        "applies_to": "PAID_SEARCH",
    }
    paid = client.post(f"/api/programs/{program_id}/evidence", json=paid_payload)
    assert paid.status_code == 200, paid.text
    assert paid.json()["proposal_state"] == "PROPOSED"
    assert paid.json()["program_gate_status"] == "WARNING_TERMS_UNVERIFIED"
    paid_review = client.post(
        f"/api/programs/{program_id}/evidence/{paid.json()['evidence']['id']}/review",
        json={"action": "ACCEPT", "reviewed_by": "Tran"},
    )
    assert paid_review.status_code == 200, paid_review.text
    assert paid_review.json()["program_gate_status"] == "WARNING_TERMS_UNVERIFIED"

    non_brand_payload = {
        **paid_payload,
        "excerpt": "Generic non-brand keywords are permitted.",
        "applies_to": "NON_BRAND",
    }
    non_brand = client.post(f"/api/programs/{program_id}/evidence", json=non_brand_payload)
    assert non_brand.status_code == 200, non_brand.text
    assert non_brand.json()["program_gate_status"] == "WARNING_TERMS_UNVERIFIED"
    non_brand_review = client.post(
        f"/api/programs/{program_id}/evidence/{non_brand.json()['evidence']['id']}/review",
        json={"action": "ACCEPT", "reviewed_by": "Tran"},
    )
    assert non_brand_review.status_code == 200, non_brand_review.text
    assert non_brand_review.json()["program_gate_status"] == "TERMS_OK"

    duplicate = client.post(f"/api/programs/{program_id}/evidence", json=non_brand_payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    programs = client.get("/api/programs").json()
    assert programs[0]["evidence_count"] == 2
    assert programs[0]["gate_status"] == "TERMS_OK"


def test_commission_csv_preview_commit_dedupe_and_state_update() -> None:
    _clear_program_finance()
    csv_data = (
        b"transaction_id,amount,currency,status,date,subid\n"
        b"t-1,10.50,USD,pending,2026-08-01,missing-subid\n"
        b"t-2,25,USD,paid,2026-08-02,\n"
        b"t-2,25,USD,paid,2026-08-02,\n"
    )
    preview = client.post(
        "/api/finance/commission-import/preview",
        data={"source": "TestNet"},
        files={"file": ("commissions.csv", csv_data, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["rows_read"] == 3
    assert body["valid_rows"] == 2
    assert body["duplicates_in_file"] == 1
    assert body["unattributed_rows"] == 2

    committed = client.post(
        "/api/finance/commission-import/commit",
        data={"source": "TestNet"},
        files={"file": ("commissions.csv", csv_data, "text/csv")},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["rows_written"] == 2

    repeated = client.post(
        "/api/finance/commission-import/preview",
        data={"source": "TestNet"},
        files={"file": ("commissions.csv", csv_data, "text/csv")},
    ).json()
    assert repeated["valid_rows"] == 0
    assert repeated["duplicates_existing"] == 2

    update_csv = (
        b"transaction_id,amount,currency,status,date\n"
        b"t-1,10.50,USD,approved,2026-08-01\n"
    )
    update_preview = client.post(
        "/api/finance/commission-import/preview",
        data={"source": "TestNet"},
        files={"file": ("update.csv", update_csv, "text/csv")},
    ).json()
    assert update_preview["valid_rows"] == 1
    assert update_preview["updates_existing"] == 1
    updated = client.post(
        "/api/finance/commission-import/commit",
        data={"source": "TestNet"},
        files={"file": ("update.csv", update_csv, "text/csv")},
    )
    assert updated.status_code == 200
    assert updated.json()["rows_written"] == 1

    summary = client.get("/api/finance/summary").json()
    usd = summary["currencies"][0]
    assert float(usd["pending_nominal"]) == 0
    assert float(usd["recognized_revenue"]) == 35.5
    assert float(usd["cash_received"]) == 25


def test_backup_api_creates_integrity_checked_sqlite_copy() -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.exec_driver_sql("DELETE FROM alembic_version")
        connection.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES ('b84d0e26c104')"
        )
    response = client.post("/api/system/backups", json={})
    assert response.status_code == 200, response.text
    info = response.json()["backup"]
    path = Path(info["database_file"])
    assert path.exists()
    assert path.stat().st_size == info["size_bytes"]
    assert len(info["sha256"]) == 64
    listed = client.get("/api/system/backups")
    assert listed.status_code == 200
    assert any(item["name"] == info["name"] for item in listed.json())
    shutil.rmtree(backup_root() / info["name"], ignore_errors=True)
