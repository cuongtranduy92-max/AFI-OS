from __future__ import annotations

import json
import urllib.error
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import SyncStatus
from afi_os.models import AdsAccount, SyncRun
from afi_os.services import google_ads_api
from afi_os.services.google_ads_api import GoogleAdsApiError
from afi_os.services.google_ads_api_sync import (
    AUTH_RETRY_INTERVAL,
    CONNECTOR,
    SYNC_INTERVAL,
    clear_google_ads_api_sync_request,
    google_ads_api_sync_due_at,
    google_ads_api_sync_is_due,
    google_ads_api_sync_requested,
    request_google_ads_api_sync,
    sync_google_ads_api,
)
from afi_os.services.google_ads_keychain import CORE_CREDENTIAL_LABELS
from afi_os.services.operations import operations_inbox


class _Response:
    def __init__(self, payload) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _payload() -> list[dict]:
    return [
        {
            "results": [
                {
                    "customer": {
                        "id": "1234567890",
                        "descriptiveName": "Google Ads",
                        "currencyCode": "VND",
                    },
                    "campaign": {
                        "id": "24116162130",
                        "name": "Campaign",
                        "status": "ENABLED",
                        "advertisingChannelType": "SEARCH",
                    },
                    "segments": {"date": "2026-08-10"},
                    "metrics": {
                        "costMicros": "1000000",
                        "impressions": "1",
                        "clicks": "1",
                        "conversions": "0",
                    },
                }
            ]
        }
    ]


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://googleads.googleapis.com/fixed",
        code,
        "sanitized test",
        hdrs=None,
        fp=None,
    )


def _seed_account() -> None:
    with SessionLocal() as db:
        db.add(
            AdsAccount(
                external_id="123-456-7890",
                name="Google Ads",
                currency="VND",
            )
        )
        db.commit()


def _checker(label: str) -> bool:
    return label in CORE_CREDENTIAL_LABELS


def _reader(label: str) -> str:
    return {
        "developer-token": "developer-secret-value",
        "oauth-client-id": "123.apps.googleusercontent.com",
        "oauth-client-secret": "client-secret-value",
        "refresh-token": "refresh-secret-value",
    }[label]


def test_rate_limit_is_retried_twice_then_read_succeeds() -> None:
    calls = 0
    delays: list[int] = []

    def opener(_request, timeout: int):
        nonlocal calls
        calls += 1
        assert timeout == 60
        if calls < 3:
            raise _http_error(429)
        return _Response(_payload())

    rows = google_ads_api.search_campaign_metrics(
        customer_id="1234567890",
        access_token="access-token",
        developer_token="developer-token",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 10),
        opener=opener,
        sleeper=delays.append,
    )
    assert calls == 3
    assert delays == [1, 2]
    assert len(rows) == 1


def test_auth_failure_is_not_retried_and_is_classified() -> None:
    calls = 0

    def opener(_request, timeout: int):
        nonlocal calls
        calls += 1
        raise _http_error(401)

    with pytest.raises(GoogleAdsApiError) as captured:
        google_ads_api.search_campaign_metrics(
            customer_id="1234567890",
            access_token="access-token",
            developer_token="developer-token",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            opener=opener,
            sleeper=lambda _delay: pytest.fail("auth must not retry"),
        )
    assert calls == 1
    assert captured.value.category == "AUTH_FAILED"
    assert "access-token" not in str(captured.value)


def test_oauth_invalid_grant_http_400_requires_login_without_retry() -> None:
    calls = 0

    def opener(_request, timeout: int):
        nonlocal calls
        calls += 1
        raise _http_error(400)

    with pytest.raises(GoogleAdsApiError) as captured:
        google_ads_api.refresh_access_token(
            client_id="123.apps.googleusercontent.com",
            client_secret="client-secret",
            refresh_token="refresh-secret",
            opener=opener,
            sleeper=lambda _delay: pytest.fail("invalid_grant must not retry"),
        )
    assert calls == 1
    assert captured.value.category == "AUTH_FAILED"


def test_failed_sync_persists_sanitized_status_and_requests_login_only_for_auth() -> None:
    _seed_account()

    def auth_failure(**_kwargs):
        raise GoogleAdsApiError("Google từ chối credential", category="AUTH_FAILED")

    with SessionLocal() as db:
        with pytest.raises(GoogleAdsApiError, match="từ chối"):
            sync_google_ads_api(
                db,
                now=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
                credential_checker=_checker,
                credential_reader=_reader,
                token_refresher=auth_failure,
                metrics_searcher=lambda **_kwargs: pytest.fail("must not search"),
            )
        sync = db.scalar(select(SyncRun).where(SyncRun.connector == CONNECTOR))
        inbox = operations_inbox(db, today=date(2026, 8, 11))
    assert sync is not None and sync.status == SyncStatus.AUTH_FAILED
    assert sync.metadata_json["requires_user"] is True
    assert sync.metadata_json["write_operations_enabled"] is False
    assert all(secret not in (sync.error_summary or "") for secret in _reader_values())
    item = next(item for item in inbox["items"] if item["key"] == "GOOGLE_ADS_API_SYNC_ERROR")
    assert item["requires_user"] is True
    assert "SETUP-GOOGLE-ADS-READ-ONLY.command" in item["detail"]


def _reader_values() -> list[str]:
    return [_reader(label) for label in CORE_CREDENTIAL_LABELS]


@pytest.mark.parametrize(
    ("status", "interval"),
    [
        (SyncStatus.SUCCESS, SYNC_INTERVAL),
        (SyncStatus.ERROR, SYNC_INTERVAL),
        (SyncStatus.RATE_LIMITED, SYNC_INTERVAL),
        (SyncStatus.AUTH_FAILED, AUTH_RETRY_INTERVAL),
    ],
)
def test_api_cadence_uses_status_specific_retry_window(
    status: SyncStatus,
    interval: timedelta,
) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    attempted_at = now - interval + timedelta(minutes=1)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector=CONNECTOR,
                started_at=attempted_at - timedelta(minutes=1),
                ended_at=attempted_at,
                status=status,
                rows_read=0,
                rows_written=0,
                metadata_json={"write_operations_enabled": False},
            )
        )
        db.commit()
        assert google_ads_api_sync_due_at(db, now=now) == attempted_at + interval
        assert google_ads_api_sync_is_due(db, now=now) is False
        assert google_ads_api_sync_is_due(
            db,
            now=attempted_at + interval,
        ) is True


def test_api_sync_request_is_secret_free_one_shot(tmp_path) -> None:
    requested_at = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    path = request_google_ads_api_sync(
        project_root=tmp_path,
        now=requested_at,
    )

    assert path.read_text(encoding="utf-8").strip() == requested_at.isoformat()
    assert path.stat().st_mode & 0o777 == 0o600
    assert google_ads_api_sync_requested(project_root=tmp_path) is True

    clear_google_ads_api_sync_request(project_root=tmp_path)
    assert google_ads_api_sync_requested(project_root=tmp_path) is False


def test_rate_limited_sync_is_warning_only_and_will_retry_next_cycle() -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector=CONNECTOR,
                started_at=now,
                ended_at=now,
                status=SyncStatus.RATE_LIMITED,
                rows_read=0,
                rows_written=0,
                error_summary="Google Ads tạm giới hạn",
                metadata_json={
                    "requires_user": False,
                    "max_retry_attempts": 3,
                    "write_operations_enabled": False,
                    "csv_fallback_enabled": True,
                },
            )
        )
        db.commit()
        inbox = operations_inbox(db, today=now.date())
    item = next(item for item in inbox["items"] if item["key"] == "GOOGLE_ADS_API_SYNC_ERROR")
    assert item["requires_user"] is False
    assert item["severity"] == "WARNING"
    assert "tự thử lại" in item["detail"]
