from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from afi_os.api import operations as operations_api
from afi_os.db import Base, SessionLocal, engine
from afi_os.main import app
from afi_os.models import AdsAccount
from afi_os.services.google_ads_readiness import (
    CREDENTIAL_LABELS,
    google_ads_readiness,
    keychain_credential_present,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_readiness_requires_account_before_credentials() -> None:
    with SessionLocal() as db:
        result = google_ads_readiness(db, credential_checker=lambda _label: False)
    assert result["status"] == "ACCOUNT_REQUIRED"
    assert result["customer_ids"] == []
    assert result["write_operations_enabled"] is False
    assert result["csv_fallback_enabled"] is True


def test_existing_customer_is_normalized_and_missing_secrets_are_names_only() -> None:
    with SessionLocal() as db:
        db.add(
            AdsAccount(
                external_id="123-456-7890",
                name="Google Ads",
                currency="VND",
            )
        )
        db.commit()
        result = google_ads_readiness(db, credential_checker=lambda _label: False)
    assert result["status"] == "CREDENTIALS_REQUIRED"
    assert result["customer_ids"] == ["1234567890"]
    assert result["customer_count"] == 1
    assert len(result["missing_credentials"]) == len(CREDENTIAL_LABELS)
    assert all("token-value" not in item for item in result["missing_credentials"])
    assert result["login_customer_id_configured"] is False


def test_all_keychain_entries_make_read_only_preflight_ready() -> None:
    with SessionLocal() as db:
        db.add(
            AdsAccount(
                external_id="1234567890",
                name="Google Ads",
                currency="VND",
            )
        )
        db.commit()
        result = google_ads_readiness(db, credential_checker=lambda _label: True)
    assert result["status"] == "READY"
    assert result["missing_credentials"] == []
    assert all(result["credentials_present"].values())
    assert result["mode"] == "READ_ONLY_REPORTING"
    assert result["write_operations_enabled"] is False
    assert result["login_customer_id_configured"] is True


def test_keychain_checker_rejects_unknown_label_without_shelling_out() -> None:
    assert keychain_credential_present("attacker-controlled") is False


def test_readiness_api_never_returns_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "status": "CREDENTIALS_REQUIRED",
        "mode": "READ_ONLY_REPORTING",
        "customer_ids": ["1234567890"],
        "customer_count": 1,
        "credentials_present": {label: False for label in CREDENTIAL_LABELS},
        "missing_credentials": ["Developer Token"],
        "manager_customer_id_required_only_for_manager_access": True,
        "login_customer_id_configured": False,
        "two_step_verification_external_check": True,
        "write_operations_enabled": False,
        "csv_fallback_enabled": True,
        "api_center_url": "https://ads.google.com/aw/apicenter",
    }
    monkeypatch.setattr(operations_api, "google_ads_readiness", lambda _db: payload)
    response = client.get("/api/operations/google-ads-readiness")
    assert response.status_code == 200
    assert response.json() == payload
    assert "super-secret-value" not in response.text
