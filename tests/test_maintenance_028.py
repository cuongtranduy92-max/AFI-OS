from __future__ import annotations

import importlib.util
import plistlib
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from afi_os import maintenance as maintenance_module
from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import ResearchStatus, SyncStatus
from afi_os.maintenance import (
    backup_is_due,
    maintenance_lock,
    run_maintenance,
    terms_refresh_is_due,
)
from afi_os.models import Merchant, Program, SyncRun, TermsResearchRun

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAUNCHD_PATH = REPOSITORY_ROOT / "scripts/launchd_manager.py"
SPEC = importlib.util.spec_from_file_location("launchd_manager_028", LAUNCHD_PATH)
assert SPEC is not None and SPEC.loader is not None
LAUNCHD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHD)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program(domain: str = "merchant.example.org") -> None:
    with SessionLocal() as db:
        merchant = Merchant(name="Merchant", website_domain=domain)
        db.add(merchant)
        db.flush()
        db.add(Program(merchant_id=merchant.id, name="Merchant Affiliate Program"))
        db.commit()


def test_maintenance_backs_up_refreshes_stale_terms_and_records_sync() -> None:
    _program()
    now = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    backup_calls: list[str] = []
    collected: list[str] = []

    def backup_creator(*, prefix: str):
        backup_calls.append(prefix)
        return {"name": "scheduled-test", "created_at": now.isoformat()}

    def collector(db, domain: str):
        collected.append(domain)
        return {
            "run": SimpleNamespace(status=ResearchStatus.PROPOSAL_READY),
            "imported_evidence": 2,
            "imported": 1,
        }

    with SessionLocal() as db:
        report = run_maintenance(
            db,
            now=now,
            collector=collector,
            backup_creator=backup_creator,
            backup_lister=lambda: [],
        )

    assert backup_calls == ["scheduled"]
    assert collected == ["merchant.example.org"]
    assert report["sync_status"] == "SUCCESS"
    assert report["terms_checked"][0]["permissions_changed"] is False
    assert report["normalization"]["missing_rows"] == 0
    with SessionLocal() as db:
        sync = db.scalar(select(SyncRun).where(SyncRun.connector == "AFI_OS_MAINTENANCE"))
        assert sync is not None
        assert sync.status == SyncStatus.SUCCESS
        assert sync.rows_read == 1
        assert sync.rows_written == 4
        assert sync.metadata_json["project_sync"] == {
            "scanned": 1,
            "created": 1,
            "linked": 0,
            "preserved": 0,
        }


def test_maintenance_skips_fresh_research_and_recent_scheduled_backup() -> None:
    _program()
    now = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                domain="merchant.example.org",
                status=ResearchStatus.PROPOSAL_READY,
                checked_at=now - timedelta(hours=1),
                discovery_confidence=0.9,
                source_urls=[],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash="t" * 64,
            )
        )
        db.commit()

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("fresh work should be skipped")

    recent_backup = {
        "name": "scheduled-recent",
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "database_status": "OK",
    }
    with SessionLocal() as db:
        report = run_maintenance(
            db,
            now=now,
            collector=should_not_run,
            backup_creator=should_not_run,
            backup_lister=lambda: [recent_backup],
        )
    assert report["backup"] is None
    assert report["terms_checked"] == []
    assert report["terms_skipped_fresh"] == ["merchant.example.org"]
    assert report["sync_status"] == "SUCCESS"
    assert backup_is_due([recent_backup], now) is False


def test_terms_refresh_uses_recheck_heartbeat_without_changing_source_date() -> None:
    now = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    source_checked_at = now - timedelta(hours=40)
    with SessionLocal() as db:
        run = TermsResearchRun(
            domain="merchant.example.org",
            status=ResearchStatus.PROPOSAL_READY,
            checked_at=source_checked_at,
            created_at=source_checked_at,
            updated_at=now - timedelta(hours=1),
            discovery_confidence=0.9,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="h" * 64,
        )
        db.add(run)
        db.commit()
        assert terms_refresh_is_due(db, run.domain, now) is False
        assert run.checked_at == source_checked_at

        run.updated_at = now - timedelta(hours=25)
        db.commit()
        assert terms_refresh_is_due(db, run.domain, now) is True
        assert run.checked_at == source_checked_at


def test_terms_refresh_selects_latest_heartbeat_across_multiple_runs() -> None:
    now = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                TermsResearchRun(
                    domain="merchant.example.org",
                    status=ResearchStatus.PROPOSAL_READY,
                    checked_at=now - timedelta(hours=30),
                    created_at=now - timedelta(hours=30),
                    updated_at=now - timedelta(hours=30),
                    discovery_confidence=0.9,
                    source_urls=[],
                    permission_proposals=[],
                    imported_fact_ids=[],
                    run_hash="older-heartbeat-newer-source".ljust(64, "a"),
                ),
                TermsResearchRun(
                    domain="merchant.example.org",
                    status=ResearchStatus.MANUAL_INPUT_REQUIRED,
                    checked_at=now - timedelta(hours=40),
                    created_at=now - timedelta(hours=40),
                    updated_at=now - timedelta(hours=1),
                    discovery_confidence=0,
                    source_urls=[],
                    permission_proposals=[],
                    imported_fact_ids=[],
                    run_hash="newest-heartbeat-older-source".ljust(64, "b"),
                ),
            ]
        )
        db.commit()

        assert terms_refresh_is_due(db, "merchant.example.org", now) is False


def test_terms_schedule_grace_prevents_missing_six_and_twenty_four_hour_slots() -> None:
    now = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    with SessionLocal() as db:
        retry = TermsResearchRun(
            domain="retry.example.org",
            status=ResearchStatus.RETRY_REQUIRED,
            checked_at=now - timedelta(hours=5, minutes=59),
            created_at=now - timedelta(hours=5, minutes=59),
            updated_at=now - timedelta(hours=5, minutes=59),
            discovery_confidence=0,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="retry-at-six-hours".ljust(64, "r"),
        )
        manual = TermsResearchRun(
            domain="manual.example.org",
            status=ResearchStatus.MANUAL_INPUT_REQUIRED,
            checked_at=now - timedelta(hours=7),
            created_at=now - timedelta(hours=7),
            updated_at=now - timedelta(hours=7),
            discovery_confidence=0,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="manual-still-waits".ljust(64, "m"),
        )
        stable_within_grace = TermsResearchRun(
            domain="stable-grace.example.org",
            status=ResearchStatus.PROPOSAL_READY,
            checked_at=now - timedelta(hours=23, minutes=56),
            created_at=now - timedelta(hours=23, minutes=56),
            updated_at=now - timedelta(hours=23, minutes=56),
            discovery_confidence=0.9,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="stable-within-grace".ljust(64, "s"),
        )
        stable_too_early = TermsResearchRun(
            domain="stable-early.example.org",
            status=ResearchStatus.PROPOSAL_READY,
            checked_at=now - timedelta(hours=23, minutes=54),
            created_at=now - timedelta(hours=23, minutes=54),
            updated_at=now - timedelta(hours=23, minutes=54),
            discovery_confidence=0.9,
            source_urls=[],
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash="stable-before-grace".ljust(64, "e"),
        )
        db.add_all([retry, manual, stable_within_grace, stable_too_early])
        db.commit()

        assert terms_refresh_is_due(db, retry.domain, now) is True
        assert terms_refresh_is_due(db, manual.domain, now) is False
        assert terms_refresh_is_due(db, stable_within_grace.domain, now) is True
        assert terms_refresh_is_due(db, stable_too_early.domain, now) is False


def test_maintenance_is_partial_but_continues_when_one_collector_fails() -> None:
    _program("failing.example.org")

    def failing_collector(*_args, **_kwargs):
        raise RuntimeError("simulated collector error")

    with SessionLocal() as db:
        report = run_maintenance(
            db,
            collector=failing_collector,
            backup_creator=lambda **_kwargs: {"name": "scheduled-test"},
            backup_lister=lambda: [],
        )

    assert report["sync_status"] == "PARTIAL"
    assert report["normalization"] is not None
    assert report["operations"] is not None
    assert len(report["errors"]) == 1
    assert "terms:failing.example.org" in report["errors"][0]


def test_maintenance_lock_prevents_overlapping_cycles() -> None:
    with maintenance_lock() as first:
        assert first is True
        with maintenance_lock() as second:
            assert second is False


def test_production_maintenance_runs_csv_fallback_before_read_only_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    events: list[str] = []

    def csv_importer(_db, *, now):
        events.append("csv")
        return {"status": "SUCCESS", "rows_read": 9, "rows_written": 0}

    def api_syncer(_db, *, now):
        events.append("api")
        return {
            "status": "SKIPPED_CREDENTIALS",
            "rows_read": 0,
            "rows_written": 0,
            "write_operations_enabled": False,
            "csv_fallback_enabled": True,
        }

    def commission_importer(_db, *, now):
        events.append("commission")
        return {"status": "SUCCESS", "rows_read": 0, "rows_written": 0}

    def campaign_mapper(_db):
        events.append("campaign-map")
        return {
            "campaigns_total": 1,
            "unlinked_scanned": 0,
            "mapped": 0,
            "unresolved": 0,
            "preserved_existing": 1,
        }

    monkeypatch.setattr(
        maintenance_module,
        "get_settings",
        lambda: SimpleNamespace(env="production"),
    )
    monkeypatch.setattr(
        maintenance_module,
        "import_downloaded_campaign_reports",
        csv_importer,
    )
    monkeypatch.setattr(
        maintenance_module,
        "import_downloaded_commission_reports",
        commission_importer,
    )
    recent_backup = {
        "name": "scheduled-recent",
        "created_at": now.isoformat(),
        "database_status": "OK",
    }
    with SessionLocal() as db:
        report = run_maintenance(
            db,
            now=now,
            backup_lister=lambda: [recent_backup],
            ads_api_syncer=api_syncer,
            campaign_mapper=campaign_mapper,
        )
    assert events == ["csv", "api", "commission", "campaign-map"]
    assert report["ads_api_sync"]["status"] == "SKIPPED_CREDENTIALS"
    assert report["ads_api_sync"]["write_operations_enabled"] is False
    assert report["campaign_auto_map"]["preserved_existing"] == 1
    assert report["sync_status"] == "SUCCESS"


def test_maintenance_keeps_csv_heartbeat_but_skips_fresh_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    events: list[str] = []

    monkeypatch.setattr(
        maintenance_module,
        "get_settings",
        lambda: SimpleNamespace(env="production"),
    )
    monkeypatch.setattr(
        maintenance_module,
        "google_ads_api_sync_requested",
        lambda: False,
    )
    monkeypatch.setattr(
        maintenance_module,
        "import_downloaded_campaign_reports",
        lambda _db, *, now: events.append("csv")
        or {"status": "SUCCESS", "rows_read": 9, "rows_written": 0},
    )
    monkeypatch.setattr(
        maintenance_module,
        "import_downloaded_commission_reports",
        lambda _db, *, now: events.append("commission")
        or {"status": "SUCCESS", "rows_read": 0, "rows_written": 0},
    )

    def campaign_mapper(_db):
        events.append("campaign-map")
        return {
            "campaigns_total": 1,
            "unlinked_scanned": 0,
            "mapped": 0,
            "unresolved": 0,
            "preserved_existing": 1,
        }

    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="GOOGLE_ADS_API_READ_ONLY",
                started_at=now - timedelta(hours=1, minutes=1),
                ended_at=now - timedelta(hours=1),
                status=SyncStatus.SUCCESS,
                rows_read=9,
                rows_written=0,
                metadata_json={"write_operations_enabled": False},
            )
        )
        db.commit()
        report = run_maintenance(
            db,
            now=now,
            backup_lister=lambda: [
                {
                    "name": "scheduled-valid",
                    "created_at": now.isoformat(),
                    "database_status": "OK",
                }
            ],
            ads_api_syncer=lambda *_args, **_kwargs: pytest.fail(
                "fresh API must not be called"
            ),
            campaign_mapper=campaign_mapper,
        )

    assert events == ["csv", "commission", "campaign-map"]
    assert report["ads_api_sync"]["status"] == "SKIPPED_FRESH"
    assert report["ads_api_sync"]["next_attempt_at"] == (
        now + timedelta(hours=5)
    ).isoformat()
    assert report["ads_api_sync"]["write_operations_enabled"] is False
    assert report["sync_status"] == "SUCCESS"


def test_setup_request_forces_one_api_attempt_then_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
    events: list[str] = []
    monkeypatch.setattr(
        maintenance_module,
        "get_settings",
        lambda: SimpleNamespace(env="production"),
    )
    monkeypatch.setattr(
        maintenance_module,
        "google_ads_api_sync_requested",
        lambda: True,
    )
    monkeypatch.setattr(
        maintenance_module,
        "clear_google_ads_api_sync_request",
        lambda: events.append("request-cleared"),
    )
    monkeypatch.setattr(
        maintenance_module,
        "import_downloaded_campaign_reports",
        lambda _db, *, now: {"status": "SUCCESS", "rows_read": 0, "rows_written": 0},
    )
    monkeypatch.setattr(
        maintenance_module,
        "import_downloaded_commission_reports",
        lambda _db, *, now: {"status": "SUCCESS", "rows_read": 0, "rows_written": 0},
    )

    def api_syncer(_db, *, now):
        events.append("api")
        return {
            "status": "SUCCESS",
            "rows_read": 0,
            "rows_written": 0,
            "write_operations_enabled": False,
            "csv_fallback_enabled": True,
        }

    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="GOOGLE_ADS_API_READ_ONLY",
                started_at=now - timedelta(minutes=2),
                ended_at=now - timedelta(minutes=1),
                status=SyncStatus.AUTH_FAILED,
                rows_read=0,
                rows_written=0,
                metadata_json={"requires_user": True},
            )
        )
        db.commit()
        report = run_maintenance(
            db,
            now=now,
            backup_lister=lambda: [
                {
                    "name": "scheduled-valid",
                    "created_at": now.isoformat(),
                    "database_status": "OK",
                }
            ],
            ads_api_syncer=api_syncer,
        )

    assert events == ["api", "request-cleared"]
    assert report["ads_api_sync"]["status"] == "SUCCESS"
    assert report["sync_status"] == "SUCCESS"


def _fake_target(tmp_path: Path) -> Path:
    target = tmp_path / "AFI-OS"
    for relative in (".venv/bin/python", "src/afi_os/main.py", "src/afi_os/maintenance.py"):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")
    return target


def test_launchd_plists_use_non_reload_server_and_safe_maintenance_interval(
    tmp_path: Path,
) -> None:
    target = _fake_target(tmp_path)
    plists = LAUNCHD.build_plists(target)
    server = plists[LAUNCHD.SERVER_LABEL]
    maintenance = plists[LAUNCHD.MAINTENANCE_LABEL]

    assert server["KeepAlive"] is True
    assert server["RunAtLoad"] is True
    assert "--reload" not in server["ProgramArguments"]
    assert server["ProgramArguments"][1:4] == ["-m", "uvicorn", "afi_os.main:app"]
    assert server["ProgramArguments"][-4:] == ["--host", "127.0.0.1", "--port", "8765"]
    assert maintenance["StartCalendarInterval"] == [{"Minute": 0}, {"Minute": 30}]
    assert "StartInterval" not in maintenance
    assert maintenance["RunAtLoad"] is True
    assert maintenance["ProgramArguments"][-2:] == ["-m", "afi_os.maintenance"]
    assert maintenance["EnvironmentVariables"]["AFI_OS_ALLOW_DEMO_SEED"] == "false"


def test_launchd_install_and_uninstall_write_only_expected_user_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _fake_target(tmp_path)
    agents = tmp_path / "LaunchAgents"
    commands: list[list[str]] = []

    def fake_run(args: list[str], *, check: bool = True):
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(LAUNCHD, "_run", fake_run)
    monkeypatch.setattr(LAUNCHD, "service_domain", lambda: "gui/501")
    installed = LAUNCHD.install(target, agents_root=agents)
    assert installed["installed"] is True
    for label in (LAUNCHD.SERVER_LABEL, LAUNCHD.MAINTENANCE_LABEL):
        path = agents / f"{label}.plist"
        assert path.is_file()
        with path.open("rb") as handle:
            assert plistlib.load(handle)["Label"] == label
    assert ["launchctl", "kickstart", "-k", "gui/501/com.afi-os.server"] in commands
    assert [
        "launchctl",
        "kickstart",
        "-k",
        "gui/501/com.afi-os.maintenance",
    ] not in commands

    removed = LAUNCHD.uninstall(agents_root=agents)
    assert removed["installed"] is False
    assert not list(agents.glob("*.plist"))
