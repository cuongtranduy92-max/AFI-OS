from __future__ import annotations

from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AppraisalJobStatus, ProjectStage
from afi_os.main import app
from afi_os.models import (
    AdObservation,
    Advertiser,
    AdvertiserApiUsage,
    AppraisalJob,
    MetricSnapshot,
    Project,
)
from afi_os.services import appraisal_jobs
from afi_os.services.advertiser_keychain import advertiser_provider_readiness
from afi_os.services.advertiser_provider import (
    ADVERTISER_GOLDMINE_MIN,
    AdvertiserCreative,
    AdvertiserPage,
    AdvertiserProviderError,
    collect_project_advertisers,
    expand_advertisers,
    fetch_advertisers_by_domain,
    fetch_domains_by_advertiser,
    quota_status,
)

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _ready() -> dict:
    return {
        "status": "READY",
        "provider": "SERPAPI",
        "api_key_present": True,
        "setup_command": "SETUP-ADVERTISER.command",
        "secret_exposed": False,
    }


def _creative(
    advertiser_id: str,
    domain: str,
    *,
    now: datetime,
    age_days: int = 1,
    suffix: str = "1",
) -> AdvertiserCreative:
    return AdvertiserCreative(
        advertiser_id=advertiser_id,
        advertiser_name=f"Advertiser {advertiser_id}",
        creative_id=f"creative-{advertiser_id}-{suffix}",
        ad_format="TEXT",
        target_domain=domain,
        first_shown=now - timedelta(days=30),
        last_shown=now - timedelta(days=age_days),
        details_link=f"https://adstransparency.google.com/advertiser/{advertiser_id}",
    )


def test_keychain_readiness_and_setup_are_secret_free() -> None:
    ready = advertiser_provider_readiness(presence_checker=lambda: True)
    missing = advertiser_provider_readiness(presence_checker=lambda: False)
    setup = (ROOT / "SETUP-ADVERTISER.command").read_text(encoding="utf-8")

    assert ready["status"] == "READY"
    assert missing["status"] == "CONNECTION_REQUIRED"
    assert ready["secret_exposed"] is False
    assert ready["setup_command"] == "SETUP-ADVERTISER.command"
    assert "com.afi-os.advertiser" in (
        ROOT / "src/afi_os/services/advertiser_keychain.py"
    ).read_text(encoding="utf-8")
    assert "Keychain" in setup
    assert ".env" in setup
    assert "sys.argv" not in setup
    assert "sys.stdin.read()" in setup


def test_serpapi_request_shapes_and_parser() -> None:
    seen: list[dict] = []

    def transport(url: str, *, params: dict, timeout: float) -> httpx.Response:
        seen.append(dict(params))
        return httpx.Response(
            200,
            json={
                "ad_creatives": [
                    {
                        "advertiser_id": "AR123",
                        "advertiser": "Acme Ads",
                        "ad_creative_id": "CR1",
                        "format": "TEXT",
                        "first_shown": 1786000000,
                        "last_shown": 1786500000,
                        "target_domain": "https://www.acme.example/offer",
                        "details_link": "https://adstransparency.google.com/a/CR1",
                    }
                ],
                "serpapi_pagination": {"next_page_token": "next-1"},
            },
        )

    domain_page = fetch_advertisers_by_domain("acme.example", "secret", transport=transport)
    advertiser_page = fetch_domains_by_advertiser(
        ["AR123", "AR456"],
        "secret",
        next_page_token="next-1",
        transport=transport,
    )

    assert domain_page.creatives[0].target_domain == "acme.example"
    assert domain_page.next_page_token == "next-1"
    assert advertiser_page.creatives[0].advertiser_name == "Acme Ads"
    assert seen[0]["engine"] == "google_ads_transparency_center"
    assert seen[0]["text"] == "acme.example"
    assert seen[0]["num"] == 100
    assert seen[1]["advertiser_id"] == "AR123,AR456"
    assert seen[1]["next_page_token"] == "next-1"


def test_domain_check_counts_active_seven_days_and_cache_costs_no_call() -> None:
    now = datetime(2026, 8, 14, 10, tzinfo=UTC)
    calls = 0

    def fetcher(domain: str, token: str) -> AdvertiserPage:
        nonlocal calls
        calls += 1
        assert domain == "active-seven.example"
        assert token == "keychain-only"
        return AdvertiserPage(
            creatives=(
                _creative("AR-ACTIVE", domain, now=now, age_days=2),
                _creative("AR-OLD", domain, now=now, age_days=8),
            )
        )

    with SessionLocal() as db:
        project = Project(domain="active-seven.example", brand_name="Active Seven")
        db.add(project)
        db.commit()
        first = collect_project_advertisers(
            db,
            project,
            now=now,
            readiness_getter=_ready,
            credential_reader=lambda: "keychain-only",
            fetcher=fetcher,
        )
        second = collect_project_advertisers(
            db,
            project,
            now=now + timedelta(days=6),
            readiness_getter=_ready,
            credential_reader=lambda: "keychain-only",
            fetcher=fetcher,
        )
        metrics = list(
            db.query(MetricSnapshot).filter_by(project_id=project.id).all()
        )
        observations = list(
            db.query(AdObservation).filter_by(project_id=project.id).all()
        )

    assert first["active_count"] == 1
    assert first["total_ever"] == 2
    assert second["status"] == "CACHED"
    assert second["cache_hit"] is True
    assert calls == 1
    assert len(observations) == 2
    assert {item.metric_key for item in metrics} == {
        "active_advertisers_7d",
        "active_advertisers_30d",
        "independent_advertisers",
    }


def test_no_advertisers_is_a_sourced_zero_and_not_connection_missing() -> None:
    now = datetime(2026, 8, 14, 11, tzinfo=UTC)
    with SessionLocal() as db:
        project = Project(domain="no-ads.example", brand_name="No Ads")
        db.add(project)
        db.commit()
        result = collect_project_advertisers(
            db,
            project,
            now=now,
            readiness_getter=_ready,
            credential_reader=lambda: "keychain-only",
            fetcher=lambda domain, token: AdvertiserPage(creatives=()),
        )
        cached = collect_project_advertisers(
            db,
            project,
            now=now + timedelta(days=6),
            readiness_getter=lambda: pytest.fail("cache must run before readiness"),
            credential_reader=lambda: pytest.fail("cache must not read credential"),
        )
        values = {
            item.metric_key: int(item.numeric_value)
            for item in db.query(MetricSnapshot).filter_by(project_id=project.id)
        }

    assert result["status"] == "NO_DATA"
    assert cached["status"] == "NO_DATA"
    assert cached["cache_hit"] is True
    assert result["detail"] == "Không tìm thấy nhà quảng cáo nào"
    assert result["active_count"] == result["total_ever"] == 0
    assert values["active_advertisers_7d"] == 0
    assert values["independent_advertisers"] == 0


def test_expansion_paginates_marks_goldmine_and_uses_cache() -> None:
    now = datetime(2026, 10, 14, 10, tzinfo=UTC)
    calls: list[str | None] = []

    def fetcher(
        external_ids: list[str],
        token: str,
        *,
        next_page_token: str | None = None,
    ) -> AdvertiserPage:
        calls.append(next_page_token)
        assert external_ids == ["AR-GOLD"]
        if next_page_token is None:
            creatives = tuple(
                _creative(
                    "AR-GOLD",
                    f"domain-{index}.example",
                    now=now,
                    suffix=str(index),
                )
                for index in range(10)
            )
            return AdvertiserPage(creatives=creatives, next_page_token="page-2")
        return AdvertiserPage(
            creatives=tuple(
                _creative(
                    "AR-GOLD",
                    f"domain-{index}.example",
                    now=now,
                    suffix=str(index),
                )
                for index in range(10, ADVERTISER_GOLDMINE_MIN)
            )
        )

    with SessionLocal() as db:
        advertiser = Advertiser(
            external_key="AR-GOLD",
            verified_name="Gold Advertiser",
        )
        db.add(advertiser)
        db.commit()
        result = expand_advertisers(
            db,
            [advertiser.id],
            now=now,
            readiness_getter=_ready,
            credential_reader=lambda: "keychain-only",
            fetcher=fetcher,
        )
        cached = expand_advertisers(
            db,
            [advertiser.id],
            now=now + timedelta(days=6),
            readiness_getter=_ready,
            credential_reader=lambda: "keychain-only",
            fetcher=fetcher,
        )
        db.refresh(advertiser)
        used = quota_status(db, day=now.date())["used"]

    assert len(result["domains"]) == ADVERTISER_GOLDMINE_MIN
    assert result["advertisers"][0]["is_goldmine"] is True
    assert len(result["advertisers"][0]["domains"]) == ADVERTISER_GOLDMINE_MIN
    assert advertiser.domain_count == ADVERTISER_GOLDMINE_MIN
    assert advertiser.is_goldmine is True
    assert calls == [None, "page-2"]
    assert used == 2
    assert cached["cache_hit"] is True


def test_quota_warns_at_eighty_percent_and_blocks_at_limit() -> None:
    now = datetime(2026, 11, 14, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            AdvertiserApiUsage(
                usage_date=now.date(),
                call_count=200,
                endpoint="TEST",
            )
        )
        db.commit()
        assert quota_status(db, day=now.date())["state"] == "WARNING"
        db.add(
            AdvertiserApiUsage(
                usage_date=now.date(),
                call_count=50,
                endpoint="TEST",
            )
        )
        project = Project(domain="quota.example", brand_name="Quota")
        db.add(project)
        db.commit()
        assert quota_status(db, day=now.date())["state"] == "BLOCKED"
        with pytest.raises(AdvertiserProviderError) as error:
            collect_project_advertisers(
                db,
                project,
                now=now,
                force_refresh=True,
                readiness_getter=_ready,
                credential_reader=lambda: "unused",
                fetcher=lambda domain, token: pytest.fail("quota must block before fetch"),
            )

    assert error.value.status == "QUOTA_EXHAUSTED"
    assert "Hết hạn mức tháng" in error.value.detail


def test_appraisal_surfaces_quota_exhaustion_as_a_clear_block() -> None:
    payload = appraisal_jobs._result_source(
        {
            "status": "QUOTA_EXHAUSTED",
            "detail": "Hết hạn mức tháng (250/250), chờ reset hoặc nâng gói",
        },
        duration_ms=12,
    )

    assert payload["status"] == "blocked"
    assert payload["label"] == "Hết hạn mức tháng (250/250), chờ reset hoặc nâng gói"
    assert payload["retryable"] is False


def test_expansion_queue_is_discovered_and_reused_when_opened(monkeypatch) -> None:
    with SessionLocal() as db:
        advertiser = Advertiser(
            external_key="AR-QUEUE",
            verified_name="Queue Advertiser",
        )
        db.add(advertiser)
        db.commit()
        advertiser_id = advertiser.id

    queued = client.post(
        "/api/ad-intelligence/discovered-domains/queue",
        json={"domain": "discovered.example", "advertiser_id": advertiser_id},
    )
    assert queued.status_code == 200, queued.text
    body = queued.json()
    assert body["project_state"] == "DISCOVERED"
    assert body["auto_started"] is False

    completed: Future = Future()
    completed.set_result({})
    monkeypatch.setattr(appraisal_jobs, "_submit_source", lambda *args: completed)
    with SessionLocal() as db:
        queued_job = db.get(AppraisalJob, body["job_id"])
        project = db.get(Project, body["project_id"])
        assert queued_job is not None
        assert queued_job.status == AppraisalJobStatus.QUEUED
        assert project is not None and project.stage == ProjectStage.DISCOVERED
        opened = appraisal_jobs.create_appraisal_job(
            db,
            "discovered.example",
            wait_for_keyword=False,
        )

    assert opened.job_id == body["job_id"]


def test_ui_exposes_quota_watchlist_active_count_and_no_periodic_scan() -> None:
    script = (ROOT / "apps/web/app.js").read_text(encoding="utf-8")
    html = (ROOT / "apps/web/index.html").read_text(encoding="utf-8")

    assert "Đang chạy 7 ngày" in script
    assert "Tổng từng thấy" in script
    assert "quảng cáo · ${advertiser.last_seen_at" in script
    assert "MỎ VÀNG" in script
    assert "Còn chạy gì nữa" in script
    assert "Quét nhóm ${Math.min(5, data.advertisers.length)} advertiser" in script
    assert "Đưa vào hàng đợi kiểm tra" in script
    assert "data-watch-rescan" in script
    assert "Đang kiểm tra quota" in html
    assert "Không quét định kỳ" in html
    assert "setInterval" not in script
