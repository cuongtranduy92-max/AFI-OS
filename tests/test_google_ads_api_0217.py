from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.models import (
    AdsAccount,
    AuditLog,
    Campaign,
    CampaignDailyStat,
    CampaignProgramLink,
    Merchant,
    Program,
    Spend,
    SyncRun,
)
from afi_os.services import google_ads_api
from afi_os.services.google_ads_api import GoogleAdsApiError, GoogleAdsCampaignMetric
from afi_os.services.google_ads_api_sync import CONNECTOR, sync_google_ads_api
from afi_os.services.google_ads_keychain import CORE_CREDENTIAL_LABELS


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


def _api_payload(*, cost_micros: str = "149291000000") -> list[dict]:
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
                        "name": "fliki.ai 10/8/2026 - 50$",
                        "status": "ENABLED",
                        "advertisingChannelType": "SEARCH",
                    },
                    "segments": {"date": "2026-08-10"},
                    "metrics": {
                        "costMicros": cost_micros,
                        "impressions": "851",
                        "clicks": "384",
                        "conversions": 0,
                    },
                }
            ]
        }
    ]


def _metric(*, cost: str = "149291") -> GoogleAdsCampaignMetric:
    return GoogleAdsCampaignMetric(
        account_external_id="1234567890",
        account_name="Google Ads",
        campaign_external_id="24116162130",
        campaign_name="fliki.ai 10/8/2026 - 50$",
        campaign_status="ENABLED",
        channel_type="SEARCH",
        currency="VND",
        metric_date=date(2026, 8, 10),
        cost=Decimal(cost),
        impressions=851,
        clicks=384,
        conversions=Decimal("0"),
    )


def _seed_existing_csv_metric() -> tuple[int, int]:
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
            launch_gate_status="WARNING_ONLY",
        )
        db.add(campaign)
        db.flush()
        db.add_all(
            [
                CampaignProgramLink(
                    campaign_id=campaign.id,
                    program_id=program.id,
                    link_source="MANUAL",
                ),
                Spend(
                    campaign_id=campaign.id,
                    spend_date=date(2026, 8, 10),
                    amount=Decimal("149291"),
                    currency="VND",
                    source="GOOGLE_ADS_CSV",
                ),
                CampaignDailyStat(
                    campaign_id=campaign.id,
                    metric_date=date(2026, 8, 10),
                    impressions=851,
                    clicks=384,
                    conversions=Decimal("0"),
                    source="GOOGLE_ADS_CSV",
                ),
            ]
        )
        db.commit()
        return program.id, campaign.id


def _checker(label: str) -> bool:
    return label in CORE_CREDENTIAL_LABELS


def _reader(label: str) -> str:
    return {
        "developer-token": "developer-secret-value",
        "oauth-client-id": "123.apps.googleusercontent.com",
        "oauth-client-secret": "client-secret-value",
        "refresh-token": "refresh-secret-value",
    }[label]


def test_refresh_token_and_searchstream_use_only_fixed_read_endpoints() -> None:
    token_request = {}

    def token_opener(request, timeout: int):
        token_request["url"] = request.full_url
        token_request["body"] = urllib.parse.parse_qs(request.data.decode("utf-8"))
        token_request["timeout"] = timeout
        return _Response({"access_token": "short-lived-access-token"})

    access_token = google_ads_api.refresh_access_token(
        client_id="123.apps.googleusercontent.com",
        client_secret="client-secret-value",
        refresh_token="refresh-secret-value",
        opener=token_opener,
    )
    assert access_token == "short-lived-access-token"
    assert token_request["url"] == google_ads_api.TOKEN_ENDPOINT
    assert "refresh-secret-value" not in token_request["url"]
    assert token_request["body"]["grant_type"] == ["refresh_token"]

    search_request = {}

    def ads_opener(request, timeout: int):
        search_request["url"] = request.full_url
        search_request["headers"] = dict(request.header_items())
        search_request["body"] = json.loads(request.data)
        search_request["timeout"] = timeout
        return _Response(_api_payload())

    rows = google_ads_api.search_campaign_metrics(
        customer_id="123-456-7890",
        access_token=access_token,
        developer_token="developer-secret-value",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 10),
        opener=ads_opener,
    )
    assert search_request["url"].endswith(
        "/v25/customers/1234567890/googleAds:searchStream"
    )
    query = search_request["body"]["query"]
    assert query.startswith("SELECT ")
    assert "segments.date BETWEEN '2026-08-10' AND '2026-08-10'" in query
    assert all(word not in query.upper() for word in ("MUTATE", "UPDATE", "REMOVE"))
    assert search_request["timeout"] == 60
    assert rows[0].cost == Decimal("149291")
    assert rows[0].impressions == 851


def test_query_and_response_validation_reject_unsafe_or_inconsistent_data() -> None:
    with pytest.raises(GoogleAdsApiError, match="tối đa"):
        google_ads_api.build_campaign_metrics_query(
            date(2026, 7, 1),
            date(2026, 8, 10),
        )
    with pytest.raises(GoogleAdsApiError, match="10 chữ số"):
        google_ads_api.search_campaign_metrics(
            customer_id="../../attacker",
            access_token="access",
            developer_token="developer",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            opener=lambda *_args, **_kwargs: _Response([]),
        )
    wrong_customer = _api_payload()
    wrong_customer[0]["results"][0]["customer"]["id"] = "1111111111"
    with pytest.raises(GoogleAdsApiError, match="sai Customer ID"):
        google_ads_api.search_campaign_metrics(
            customer_id="1234567890",
            access_token="access",
            developer_token="developer",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            opener=lambda *_args, **_kwargs: _Response(wrong_customer),
        )


def test_api_preview_matches_hyphenated_local_account_without_creating_duplicates() -> None:
    _seed_existing_csv_metric()
    captured = {}

    def token_refresher(**kwargs):
        captured["token"] = kwargs
        return "short-lived-access-token"

    def searcher(**kwargs):
        captured["search"] = kwargs
        return [_metric()]

    with SessionLocal() as db:
        result = sync_google_ads_api(
            db,
            now=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            commit=False,
            credential_checker=_checker,
            credential_reader=_reader,
            token_refresher=token_refresher,
            metrics_searcher=searcher,
        )
        assert db.scalar(select(func.count()).select_from(AdsAccount)) == 1
        assert db.scalar(select(func.count()).select_from(SyncRun)) == 0
    assert result["status"] == "PREVIEW"
    assert result["reconciliation_before_commit"] == {
        "matched_rows": 1,
        "different_rows": 0,
        "new_rows": 0,
        "mapped_rows": 1,
        "unmapped_rows": 0,
    }
    assert captured["search"]["customer_id"] == "1234567890"
    assert captured["token"]["refresh_token"] == "refresh-secret-value"
    assert "refresh-secret-value" not in json.dumps(result)


def test_api_commit_updates_canonical_google_row_and_preserves_terms_and_mapping() -> None:
    program_id, campaign_id = _seed_existing_csv_metric()

    with SessionLocal() as db:
        result = sync_google_ads_api(
            db,
            now=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            credential_checker=_checker,
            credential_reader=_reader,
            token_refresher=lambda **_kwargs: "short-lived-access-token",
            metrics_searcher=lambda **_kwargs: [_metric(cost="150000")],
        )
        spend = db.scalar(select(Spend).where(Spend.campaign_id == campaign_id))
        link = db.scalar(
            select(CampaignProgramLink).where(
                CampaignProgramLink.campaign_id == campaign_id
            )
        )
        program = db.get(Program, program_id)
        sync = db.scalar(select(SyncRun).where(SyncRun.connector == CONNECTOR))
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.entity_type == "campaign_import")
            .order_by(AuditLog.id.desc())
        )
        assert spend is not None and spend.amount == Decimal("150000")
        assert spend.source == "GOOGLE_ADS_CSV"
        assert db.scalar(select(func.count()).select_from(Spend)) == 1
        assert link is not None and link.program_id == program_id
        assert link.link_source == "MANUAL"
        assert program is not None
        assert program.paid_search_permission.value == "NOT_CHECKED"
        assert sync is not None
        assert sync.metadata_json["write_operations_enabled"] is False
        assert audit is not None and audit.actor == "auto-google-ads-api"
    assert result["status"] == "SUCCESS"
    assert result["rows_written"] == 1
    assert result["reconciliation_before_commit"]["different_rows"] == 1


def test_missing_credentials_skip_before_any_secret_read_or_network_call() -> None:
    with SessionLocal() as db:
        db.add(
            AdsAccount(
                external_id="123-456-7890",
                name="Google Ads",
                currency="VND",
            )
        )
        db.commit()
        result = sync_google_ads_api(
            db,
            credential_checker=lambda _label: False,
            credential_reader=lambda _label: pytest.fail("must not read Keychain"),
            token_refresher=lambda **_kwargs: pytest.fail("must not call Google"),
            metrics_searcher=lambda **_kwargs: pytest.fail("must not call Google Ads"),
        )
    assert result["status"] == "SKIPPED_CREDENTIALS"
    assert result["rows_written"] == 0
    assert result["csv_fallback_enabled"] is True
    assert result["write_operations_enabled"] is False
