from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.models import AdsAccount
from afi_os.services.google_ads_keychain import (
    CORE_CREDENTIAL_LABELS,
    credential_present,
)

API_CENTER_URL = "https://ads.google.com/aw/apicenter"
CREDENTIAL_LABELS = CORE_CREDENTIAL_LABELS
DISPLAY_LABELS = {
    "developer-token": "Developer Token",
    "oauth-client-id": "OAuth Client ID",
    "oauth-client-secret": "OAuth Client Secret",
    "refresh-token": "OAuth Refresh Token",
}


keychain_credential_present = credential_present


def _normalized_customer_id(value: str) -> str | None:
    normalized = value.replace("-", "").strip()
    return normalized if len(normalized) == 10 and normalized.isdigit() else None


def google_ads_readiness(
    db: Session,
    *,
    credential_checker: Callable[[str], bool] = keychain_credential_present,
) -> dict:
    accounts = list(db.scalars(select(AdsAccount).order_by(AdsAccount.id.asc())).all())
    customer_ids = sorted(
        {
            normalized
            for account in accounts
            if (normalized := _normalized_customer_id(account.external_id)) is not None
        }
    )
    credential_state = {
        label: bool(credential_checker(label)) for label in CREDENTIAL_LABELS
    }
    login_customer_id_configured = bool(credential_checker("login-customer-id"))
    missing_credentials = [
        DISPLAY_LABELS[label]
        for label in CREDENTIAL_LABELS
        if not credential_state[label]
    ]
    if not customer_ids:
        status = "ACCOUNT_REQUIRED"
    elif missing_credentials:
        status = "CREDENTIALS_REQUIRED"
    else:
        status = "READY"
    return {
        "status": status,
        "mode": "READ_ONLY_REPORTING",
        "customer_ids": customer_ids,
        "customer_count": len(customer_ids),
        "credentials_present": credential_state,
        "missing_credentials": missing_credentials,
        "manager_customer_id_required_only_for_manager_access": True,
        "login_customer_id_configured": login_customer_id_configured,
        "two_step_verification_external_check": True,
        "write_operations_enabled": False,
        "csv_fallback_enabled": True,
        "api_center_url": API_CENTER_URL,
    }
