from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from afi_os.api import appraisal as appraisal_api
from afi_os.api import portfolio
from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import ResearchStatus
from afi_os.main import app
from afi_os.models import MetricSnapshot, Project
from afi_os.services.appraisal import build_appraisal_contract
from afi_os.services.portfolio import load_portfolio_project
from afi_os.services.traffic_keychain import SUPPORTED_PROVIDERS, traffic_provider_readiness
from afi_os.services.traffic_provider import (
    APIFY_ACTOR_ID,
    APIFY_SOURCE_URL,
    TRAFFIC_VALID_DAYS,
    TrafficObservationEx,
    TrafficProviderError,
    collect_project_traffic,
    collect_project_traffic_batch,
    fetch_apify_similarweb,
    fetch_apify_similarweb_batch,
    store_traffic_observation,
)

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _ready() -> dict:
    return {
        "status": "READY",
        "provider": "APIFY",
        "api_key_present": True,
        "setup_command": "SETUP-TRAFFIC-DATA.command",
    }


def _observation(domain: str, visits: str = "123456") -> TrafficObservationEx:
    return TrafficObservationEx(
        provider="APIFY_SIMILARWEB",
        monthly_visits=Decimal(visits),
        period=date(2026, 7, 1),
        source_url=f"{APIFY_SOURCE_URL}#{domain}",
        confidence=0.75,
        top_countries=(("US", 0.42), ("GB", 0.13), ("CA", 0.08)),
    )


def test_apify_is_supported_without_exposing_keychain_secret() -> None:
    assert "APIFY" in SUPPORTED_PROVIDERS
    readiness = traffic_provider_readiness(
        presence_checker=lambda label: True,
        credential_reader=lambda label: "APIFY" if label == "provider" else "secret",
    )

    assert readiness["status"] == "READY"
    assert readiness["provider"] == "APIFY"
    assert readiness["secret_exposed"] is False
    assert "api-key-value" not in str(readiness)


def test_apify_single_parses_latest_month_and_top_five_without_leaking_token() -> None:
    calls: list[tuple[str, dict, dict, float]] = []

    def transport(url: str, *, params: dict, json: dict, timeout: float) -> httpx.Response:
        calls.append((url, params, json, timeout))
        return httpx.Response(
            200,
            json=[
                {
                    "domain": "canva.com",
                    "estimatedMonthlyVisits": {
                        "bad-date": 999,
                        "2026-06-01": 12_000,
                        "2026-07-01": 34_567,
                    },
                    "topCountryShares": [
                        {"countryCode": "IN", "share": 0.11},
                        {"countryCode": "US", "share": 0.31},
                        {"countryCode": "BR", "share": 0.08},
                        {"countryCode": "GB", "share": 0.12},
                        {"countryCode": "CA", "share": 0.09},
                        {"countryCode": "AU", "share": 0.07},
                    ],
                }
            ],
        )

    observation = fetch_apify_similarweb(
        "canva.com",
        "apify-secret-token",
        now=datetime(2026, 8, 13, tzinfo=UTC),
        transport=transport,
    )

    assert observation.monthly_visits == Decimal("34567")
    assert observation.period == date(2026, 7, 1)
    assert observation.top_countries == (
        ("US", 0.31),
        ("GB", 0.12),
        ("IN", 0.11),
        ("CA", 0.09),
        ("BR", 0.08),
    )
    assert observation.confidence == 0.75
    assert APIFY_ACTOR_ID in calls[0][0]
    assert calls[0][2] == {
        "domains": ["canva.com"],
        "mode": "base_data",
        "maxConcurrency": 1,
    }
    assert "apify-secret-token" not in observation.source_url


def test_apify_missing_or_junk_domain_is_no_data_not_zero() -> None:
    def transport(url: str, **kwargs) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "domain": "junk.invalid",
                    "estimatedMonthlyVisits": {},
                    "visits": 0,
                    "topCountryShares": [],
                }
            ],
        )

    try:
        fetch_apify_similarweb(
            "junk.invalid",
            "token",
            now=datetime(2026, 8, 13, tzinfo=UTC),
            transport=transport,
        )
    except TrafficProviderError as exc:
        assert exc.status == "NO_DATA"
    else:  # pragma: no cover - guard against silently invented zeroes
        raise AssertionError("junk domain phải trả NO_DATA")


def test_apify_snapshots_power_appraisal_and_cache_skips_second_call() -> None:
    now = datetime(2026, 8, 13, 9, tzinfo=UTC)
    fetch_count = 0
    credential_count = 0

    def fetcher(domain: str, token: str, *, now: datetime) -> TrafficObservationEx:
        nonlocal fetch_count
        fetch_count += 1
        assert token == "keychain-only"
        return _observation(domain)

    def credential_reader(label: str) -> str:
        nonlocal credential_count
        credential_count += 1
        assert label == "api-key"
        return "keychain-only"

    with SessionLocal() as db:
        project = Project(domain="apify-cache.example", brand_name="Apify Cache")
        db.add(project)
        db.commit()
        first = collect_project_traffic(
            db,
            project,
            now=now,
            readiness_getter=_ready,
            credential_reader=credential_reader,
            fetchers={"APIFY": fetcher},
        )
        second = collect_project_traffic(
            db,
            project,
            now=now + timedelta(days=44),
            readiness_getter=_ready,
            credential_reader=credential_reader,
            fetchers={"APIFY": fetcher},
        )
        db.expire_all()
        loaded = load_portfolio_project(db, project.id)
        assert loaded is not None
        contract = build_appraisal_contract(db, loaded)
        snapshots = db.query(MetricSnapshot).filter_by(project_id=project.id).all()

    assert first["status"] == "COLLECTED"
    assert second["status"] == "CACHED"
    assert second["cache_hit"] is True
    assert fetch_count == credential_count == 1
    assert {item.metric_key for item in snapshots} == {
        "website_traffic_monthly",
        "top_traffic_countries",
    }
    expected_expiry = (now + timedelta(days=TRAFFIC_VALID_DAYS)).replace(tzinfo=None)
    assert all(item.valid_until == expected_expiry for item in snapshots)
    assert contract.traffic.monthly == 123456
    assert contract.traffic.top_countries == [("US", 0.42), ("GB", 0.13), ("CA", 0.08)]
    assert contract.traffic.source_status == "ready"
    assert not any("Traffic đang chờ" in item.msg for item in contract.score.flags)
    assert "keychain-only" not in str([item.payload_json for item in snapshots])


def test_expired_cache_calls_apify_again() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    calls = 0

    def fetcher(domain: str, token: str, *, now: datetime) -> TrafficObservationEx:
        nonlocal calls
        calls += 1
        return _observation(domain, str(100_000 + calls))

    with SessionLocal() as db:
        project = Project(domain="apify-stale.example", brand_name="Apify Stale")
        db.add(project)
        db.commit()
        collect_project_traffic(
            db,
            project,
            now=now,
            readiness_getter=_ready,
            credential_reader=lambda label: "token",
            fetchers={"APIFY": fetcher},
        )
        refreshed = collect_project_traffic(
            db,
            project,
            now=now + timedelta(days=46),
            readiness_getter=_ready,
            credential_reader=lambda label: "token",
            fetchers={"APIFY": fetcher},
        )

    assert calls == 2
    assert refreshed["status"] == "COLLECTED"


def test_apify_ten_domain_batch_uses_one_actor_run_and_keeps_per_domain_no_data() -> None:
    domains = [f"batch-{index}.example" for index in range(10)]
    calls = 0

    def transport(url: str, *, params: dict, json: dict, timeout: float) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert json["domains"] == domains
        assert json["maxConcurrency"] == 10
        return httpx.Response(
            200,
            json=[
                {
                    "domain": domain,
                    "estimatedMonthlyVisits": {"2026-07-01": index * 1000 + 1000},
                    "topCountryShares": [{"countryCode": "US", "share": 0.4}],
                }
                for index, domain in enumerate(domains[:-1])
            ],
        )

    result = fetch_apify_similarweb_batch(
        domains,
        "token",
        now=datetime(2026, 8, 13, tzinfo=UTC),
        transport=transport,
    )

    assert calls == 1
    assert len(result) == 10
    assert isinstance(result[domains[-1]], TrafficProviderError)
    assert result[domains[-1]].status == "NO_DATA"  # type: ignore[union-attr]


def test_collect_batch_stores_ten_domains_once_then_uses_cache() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    calls = 0

    def batch_fetcher(domains: list[str], token: str, *, now: datetime) -> dict:
        nonlocal calls
        calls += 1
        return {
            domain: _observation(domain, str(30_000 + index))
            for index, domain in enumerate(domains)
        }

    with SessionLocal() as db:
        projects = [
            Project(domain=f"store-{index}.example", brand_name=f"Store {index}")
            for index in range(10)
        ]
        db.add_all(projects)
        db.commit()
        first = collect_project_traffic_batch(
            db,
            projects,
            now=now,
            readiness_getter=_ready,
            credential_reader=lambda label: "token",
            batch_fetcher=batch_fetcher,
        )
        second = collect_project_traffic_batch(
            db,
            projects,
            now=now + timedelta(days=10),
            readiness_getter=_ready,
            credential_reader=lambda label: "token",
            batch_fetcher=batch_fetcher,
        )

    assert calls == 1
    assert all(item["status"] == "COLLECTED" for item in first.values())
    assert all(item["status"] == "CACHED" for item in second.values())


def test_appraisal_batch_returns_fresh_traffic_for_every_domain(monkeypatch) -> None:
    calls = 0

    def fake_batch(db, projects):
        nonlocal calls
        calls += 1
        result = {}
        for project in projects:
            snapshot, created = store_traffic_observation(
                db,
                project,
                _observation(project.domain),
                now=datetime(2026, 8, 13, tzinfo=UTC),
            )
            result[project.domain] = {
                **_ready(),
                "status": "COLLECTED",
                "fields": ["website_traffic_monthly", "top_traffic_countries"],
                "detail": "batch test",
                "source_urls": [snapshot.source_url],
                "created": created,
            }
        return result

    monkeypatch.setattr(appraisal_api, "collect_project_traffic_batch", fake_batch)
    monkeypatch.setattr(
        portfolio,
        "collect_domain_proposal",
        lambda db, domain: {
            "run": SimpleNamespace(status=ResearchStatus.MANUAL_INPUT_REQUIRED),
            "program": None,
            "source_urls": [],
        },
    )
    monkeypatch.setattr(
        portfolio,
        "collect_project_keyword_metrics",
        lambda db, project: {
            "status": "CONNECTION_REQUIRED",
            "detail": "Google Ads API chưa sẵn sàng.",
            "requires_user": True,
            "fields": [],
            "source_urls": [],
        },
    )
    domains = [f"api-batch-{index}.example" for index in range(10)]

    response = client.post("/api/appraise/batch", json={"domains": domains})

    assert response.status_code == 200, response.text
    assert calls == 1
    assert [item["domain"] for item in response.json()] == domains
    assert all(item["traffic"]["monthly"] == 123456 for item in response.json())
    assert all(item["traffic"]["source_status"] == "ready" for item in response.json())


def test_ui_and_setup_command_use_batch_and_recommend_apify() -> None:
    script = (ROOT / "apps" / "web" / "app.js").read_text(encoding="utf-8")
    setup = (ROOT / "SETUP-TRAFFIC-DATA.command").read_text(encoding="utf-8")

    assert 'request("/appraise/batch"' in script
    assert ".slice(0, 50)" in script
    assert "APIFY" in setup
    assert "khuyên dùng" in setup
