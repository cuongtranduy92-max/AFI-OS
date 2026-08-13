from __future__ import annotations

from datetime import UTC, date, datetime
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
    Click,
    Commission,
    Conversion,
    FinanceSettings,
    FxRate,
    Merchant,
    Program,
    ReconciliationItem,
    Spend,
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
            ReconciliationItem,
            FxRate,
            FinanceSettings,
            Commission,
            Conversion,
            Click,
            Spend,
            Campaign,
            AdsAccount,
            Program,
            Merchant,
            AffiliateNetwork,
        ):
            db.execute(delete(model))
        db.commit()


def seed_finance_rows() -> None:
    with SessionLocal() as db:
        account = AdsAccount(
            external_id="123-456-7890",
            name="Main Ads",
            currency="VND",
            status="ACTIVE",
        )
        db.add(account)
        db.flush()
        campaign = Campaign(
            ads_account_id=account.id,
            external_id="9988",
            name="Search",
            status="ENABLED",
            channel_type="SEARCH",
            currency="VND",
            launch_gate_status="WARNING_ONLY",
        )
        db.add(campaign)
        db.flush()
        db.add(
            Spend(
                campaign_id=campaign.id,
                spend_date=date(2026, 8, 5),
                amount=Decimal("100"),
                currency="VND",
                source="GOOGLE_ADS_CSV",
                quality=DataQuality.OBSERVED,
            )
        )
        conversion = Conversion(
            external_id="test:conversion:1",
            occurred_at=datetime(2026, 8, 5, tzinfo=UTC),
            currency="USD",
            status="CONVERTED_PENDING",
            source="TEST",
            raw_hash="finance-024-conversion",
            quality=DataQuality.OBSERVED,
        )
        db.add(conversion)
        db.flush()
        db.add(
            Commission(
                external_id="TEST:commission:1",
                conversion_id=conversion.id,
                amount=Decimal("10"),
                currency="USD",
                state=CommissionState.PAID,
                occurred_at=datetime(2026, 8, 5, tzinfo=UTC),
                source="TEST",
                quality=DataQuality.OBSERVED,
            )
        )
        db.commit()


def rate_payload(rate: str, confidence: str = "0.9") -> dict:
    return {
        "rate_date": "2026-08-01",
        "from_currency": "USD",
        "to_currency": "VND",
        "rate": rate,
        "source_name": "Official Bank",
        "source_url": f"https://bank.example/fx/{rate}",
        "checked_at": "2026-08-01T08:00:00Z",
        "confidence": confidence,
        "actor": "Tran",
    }


def test_currency_normalization_requires_reviewed_sourced_rate() -> None:
    seed_finance_rows()
    normalized = client.post("/api/finance/normalize")
    assert normalized.status_code == 200, normalized.text
    assert normalized.json()["normalized_rows"] == 1
    assert normalized.json()["missing_pairs"] == {"USD->VND": 1}

    before = client.get("/api/finance/normalization").json()
    assert before["base_currency"] == "VND"
    assert before["normalized_spend"] == "100.000000"
    assert before["commission_missing"] == 1
    assert before["actual_net_cash"] == "-100.000000"

    low = client.post("/api/finance/fx-rates", json=rate_payload("25000", "0.5"))
    assert low.status_code == 200, low.text
    low_id = low.json()["rate"]["id"]
    rejected_accept = client.post(
        f"/api/finance/fx-rates/{low_id}/review",
        json={"action": "ACCEPT", "reviewed_by": "Tran"},
    )
    assert rejected_accept.status_code == 422

    proposed = client.post("/api/finance/fx-rates", json=rate_payload("25000"))
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["duplicate"] is True
    repeated = client.post("/api/finance/fx-rates", json=rate_payload("25000"))
    assert repeated.json()["duplicate"] is True
    rate_id = proposed.json()["rate"]["id"]
    accepted = client.post(
        f"/api/finance/fx-rates/{rate_id}/review",
        json={"action": "ACCEPT", "reviewed_by": "Tran"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["normalization"]["normalized_rows"] == 2

    after = client.get("/api/finance/normalization").json()
    assert after["normalized_spend"] == "100.000000"
    assert after["cash_received"] == "250000.000000"
    assert after["actual_net_cash"] == "249900.000000"
    assert after["commission_missing"] == 0

    conflicting = client.post("/api/finance/fx-rates", json=rate_payload("26000"))
    conflict_id = conflicting.json()["rate"]["id"]
    blocked = client.post(
        f"/api/finance/fx-rates/{conflict_id}/review",
        json={"action": "ACCEPT", "reviewed_by": "Tran"},
    )
    assert blocked.status_code == 422
    assert client.get("/api/finance/normalization").json()["cash_received"] == "250000.000000"


def test_reconciliation_queue_tracks_attribution_duplicates_and_conflicts() -> None:
    data = (
        b"transaction_id,amount,currency,status,date\n"
        b"t-1,10,USD,pending,2026-08-01\n"
        b"t-1,10,USD,pending,2026-08-01\n"
        b"t-2,20,USD,pending,2026-08-02\n"
        b"t-2,25,USD,pending,2026-08-02\n"
    )
    preview = client.post(
        "/api/finance/commission-import/preview",
        data={"source": "TestNet"},
        files={"file": ("commissions.csv", data, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 2
    assert preview.json()["duplicates_in_file"] == 1
    assert preview.json()["conflict_count"] == 1

    committed = client.post(
        "/api/finance/commission-import/commit",
        data={"source": "TestNet"},
        files={"file": ("commissions.csv", data, "text/csv")},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["rows_written"] == 2

    queue = client.get("/api/finance/reconciliation").json()
    assert queue["status_counts"] == {"UNATTRIBUTED": 2}
    assert queue["open_issue_counts"] == {"CONFLICT": 1, "DUPLICATE": 1}
    assert queue["open_items"] == 4

    changed_amount = (
        b"transaction_id,amount,currency,status,date\n"
        b"t-1,11,USD,approved,2026-08-01\n"
    )
    conflict_preview = client.post(
        "/api/finance/commission-import/preview",
        data={"source": "TestNet"},
        files={"file": ("changed.csv", changed_amount, "text/csv")},
    ).json()
    assert conflict_preview["valid_rows"] == 0
    assert conflict_preview["conflict_count"] == 1
    conflict_commit = client.post(
        "/api/finance/commission-import/commit",
        data={"source": "TestNet"},
        files={"file": ("changed.csv", changed_amount, "text/csv")},
    )
    assert conflict_commit.json()["rows_written"] == 0
    commission = client.get("/api/finance/commissions").json()
    t1 = next(item for item in commission if item["external_id"] == "TESTNET:t-1")
    assert t1["amount"] == "10.000000"
    assert t1["state"] == "PENDING"

    conflict_item = next(
        item
        for item in client.get("/api/finance/reconciliation").json()["items"]
        if item["status"] == "CONFLICT" and item["entity_type"] == "COMMISSION"
    )
    resolved = client.post(
        f"/api/finance/reconciliation/{conflict_item['id']}/resolve",
        json={"resolved_by": "Tran", "note": "Giữ số tiền hiện tại; chờ network xác minh."},
    )
    assert resolved.status_code == 200, resolved.text
    resolved_item = next(
        item for item in resolved.json()["items"] if item["id"] == conflict_item["id"]
    )
    assert resolved_item["resolved_by"] == "Tran"

    state_update = (
        b"transaction_id,amount,currency,status,date\n"
        b"t-1,10,USD,approved,2026-08-01\n"
    )
    safe_preview = client.post(
        "/api/finance/commission-import/preview",
        data={"source": "TestNet"},
        files={"file": ("state.csv", state_update, "text/csv")},
    ).json()
    assert safe_preview["valid_rows"] == 1
    assert safe_preview["updates_existing"] == 1
    safe_commit = client.post(
        "/api/finance/commission-import/commit",
        data={"source": "TestNet"},
        files={"file": ("state.csv", state_update, "text/csv")},
    )
    assert safe_commit.json()["rows_written"] == 1
    commission = client.get("/api/finance/commissions").json()
    t1 = next(item for item in commission if item["external_id"] == "TESTNET:t-1")
    assert t1["state"] == "APPROVED"


def test_reconciliation_distinguishes_attributed_and_partial() -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Example", website_domain="example.ai")
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name="Example Affiliate")
        click = Click(
            affiliate_subid="matched-subid",
            clicked_at=datetime(2026, 8, 1, tzinfo=UTC),
            source="TEST",
            quality=DataQuality.OBSERVED,
        )
        db.add_all((program, click))
        db.commit()
        program_id = program.id

    data = (
        b"transaction_id,amount,currency,status,date,subid\n"
        b"t-matched,10,USD,approved,2026-08-01,matched-subid\n"
        b"t-partial,20,USD,approved,2026-08-01,\n"
    )
    committed = client.post(
        "/api/finance/commission-import/commit",
        data={"source": "TestNet", "program_id": str(program_id)},
        files={"file": ("attribution.csv", data, "text/csv")},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["rows_written"] == 2

    queue = client.get("/api/finance/reconciliation").json()
    assert queue["status_counts"] == {"ATTRIBUTED": 1, "PARTIAL": 1}
    attributed = next(item for item in queue["items"] if item["status"] == "ATTRIBUTED")
    partial = next(item for item in queue["items"] if item["status"] == "PARTIAL")
    assert attributed["resolved_by"] == "system"
    assert partial["resolved_at"] is None


def test_finance_ui_exposes_fx_and_reconciliation_workflows() -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="financeSettingsForm"' in page.text
    assert 'id="fxRateForm"' in page.text
    assert 'id="fxRateRows"' in page.text
    assert 'id="reconciliationRows"' in page.text

    script = client.get("/app.js")
    assert script.status_code == 200
    assert "/finance/fx-rates" in script.text
    assert "/finance/reconciliation" in script.text
    assert "/finance/normalization" in script.text
