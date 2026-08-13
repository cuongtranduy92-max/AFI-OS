from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from afi_os.api import operations as operations_api
from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import ResearchStatus, SyncStatus
from afi_os.main import app
from afi_os.models import AdsAccount, Merchant, Program, SyncRun, TermsResearchRun
from afi_os.services import runtime_status as runtime_status_module
from afi_os.services.runtime_status import (
    MAINTENANCE_LABEL,
    SERVER_LABEL,
    _next_scheduled_terms_refresh,
    launchd_service_loaded,
    runtime_status,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program(domain: str) -> int:
    with SessionLocal() as db:
        merchant = Merchant(name=domain, website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name=f"{domain} Affiliate")
        db.add(program)
        db.commit()
        return program.id


def _research(domain: str, checked_at: datetime, suffix: str) -> None:
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                domain=domain,
                status=ResearchStatus.PROPOSAL_READY,
                checked_at=checked_at,
                created_at=checked_at,
                updated_at=checked_at,
                discovery_confidence=0.9,
                source_urls=[],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash=suffix * 64,
            )
        )
        db.commit()


def test_runtime_status_reports_services_maintenance_backup_and_terms_freshness() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    _program("fresh.example.org")
    _program("stale.example.org")
    _research("fresh.example.org", now - timedelta(hours=2), "f")
    _research("stale.example.org", now - timedelta(hours=30), "s")
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="AFI_OS_MAINTENANCE",
                started_at=now - timedelta(minutes=10),
                ended_at=now - timedelta(minutes=9),
                status=SyncStatus.SUCCESS,
                rows_read=2,
                rows_written=1,
                metadata_json={
                    "campaign_auto_map": {
                        "campaigns_total": 4,
                        "unlinked_scanned": 2,
                        "mapped": 1,
                        "unresolved": 1,
                        "preserved_existing": 2,
                    }
                },
            )
        )
        db.commit()

    backups = [
        {
            "name": "manual-newer",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "size_bytes": 99,
        },
        {
            "name": "scheduled-latest",
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "size_bytes": 12345,
            "database_status": "OK",
        },
    ]
    with SessionLocal() as db:
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: backups,
        )

    assert result["status"] == "HEALTHY"
    assert result["server_service_loaded"] is True
    assert result["maintenance_service_loaded"] is True
    assert result["maintenance_status"] == "SUCCESS"
    assert result["maintenance_overdue"] is False
    assert result["campaign_auto_map_total"] == 4
    assert result["campaign_auto_map_unlinked_scanned"] == 2
    assert result["campaign_auto_map_mapped"] == 1
    assert result["campaign_auto_map_unresolved"] == 1
    assert result["campaign_auto_map_preserved_existing"] == 2
    assert result["latest_scheduled_backup_name"] == "scheduled-latest"
    assert result["latest_scheduled_backup_size_bytes"] == 12345
    assert result["programs_total"] == 2
    assert result["terms_fresh"] == 1
    assert result["terms_stale"] == 1
    assert result["terms_due_count"] == 1
    assert result["terms_retry_pending"] == 0
    assert result["terms_next_refresh_at"] == now - timedelta(hours=6)
    assert result["terms_next_scheduled_refresh_at"] == now + timedelta(minutes=20)
    assert result["programs_terms_ok"] == 0
    assert result["programs_terms_warnings"] == 2


def test_runtime_terms_freshness_uses_latest_heartbeat_across_runs() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    _program("heartbeat.example.org")
    with SessionLocal() as db:
        db.add_all(
            [
                TermsResearchRun(
                    domain="heartbeat.example.org",
                    status=ResearchStatus.PROPOSAL_READY,
                    checked_at=now - timedelta(hours=30),
                    created_at=now - timedelta(hours=30),
                    updated_at=now - timedelta(hours=30),
                    discovery_confidence=0.9,
                    source_urls=[],
                    permission_proposals=[],
                    imported_fact_ids=[],
                    run_hash="runtime-source-newer".ljust(64, "r"),
                ),
                TermsResearchRun(
                    domain="heartbeat.example.org",
                    status=ResearchStatus.MANUAL_INPUT_REQUIRED,
                    checked_at=now - timedelta(hours=40),
                    created_at=now - timedelta(hours=40),
                    updated_at=now - timedelta(hours=1),
                    discovery_confidence=0,
                    source_urls=[],
                    permission_proposals=[],
                    imported_fact_ids=[],
                    run_hash="runtime-heartbeat-newer".ljust(64, "h"),
                ),
            ]
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )

    assert result["terms_fresh"] == 1
    assert result["terms_stale"] == 0
    assert result["terms_due_count"] == 0
    assert result["terms_retry_pending"] == 0
    assert result["terms_next_refresh_at"] == now + timedelta(hours=23)
    assert result["terms_next_scheduled_refresh_at"] == now + timedelta(hours=23)
    assert result["programs_terms_ok"] == 0
    assert result["programs_terms_warnings"] == 1


def test_runtime_terms_without_research_is_due_immediately() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    _program("unchecked.example.org")
    with SessionLocal() as db:
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )

    assert result["terms_fresh"] == 0
    assert result["terms_stale"] == 1
    assert result["terms_due_count"] == 1
    assert result["terms_retry_pending"] == 0
    assert result["terms_next_refresh_at"] == now
    assert result["terms_next_scheduled_refresh_at"] == now
    assert result["programs_terms_warnings"] == 1


def test_terms_eta_skips_maintenance_slots_before_24_hour_eligibility() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    assert _next_scheduled_terms_refresh(
        now + timedelta(hours=22),
        now + timedelta(hours=5, minutes=50),
        now,
    ) == now + timedelta(hours=22, minutes=20)
    assert _next_scheduled_terms_refresh(
        now + timedelta(hours=6),
        now + timedelta(hours=6),
        now,
    ) == now + timedelta(hours=6)
    assert _next_scheduled_terms_refresh(
        now + timedelta(hours=6),
        now + timedelta(hours=5, minutes=58),
        now,
    ) == now + timedelta(hours=5, minutes=58)


def test_runtime_temporary_terms_failure_uses_six_hour_retry_window() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    _program("retry.example.org")
    with SessionLocal() as db:
        db.add(
            TermsResearchRun(
                domain="retry.example.org",
                status=ResearchStatus.RETRY_REQUIRED,
                checked_at=now - timedelta(hours=5),
                created_at=now - timedelta(hours=5),
                updated_at=now - timedelta(hours=5),
                discovery_confidence=0,
                source_urls=[],
                permission_proposals=[],
                imported_fact_ids=[],
                run_hash="runtime-retry-window".ljust(64, "r"),
            )
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )

    assert result["terms_fresh"] == 1
    assert result["terms_due_count"] == 0
    assert result["terms_retry_pending"] == 1
    assert result["terms_next_refresh_at"] == now + timedelta(hours=1)


def test_runtime_status_is_not_configured_without_agents_or_history() -> None:
    with SessionLocal() as db:
        result = runtime_status(
            db,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )
    assert result["status"] == "NOT_CONFIGURED"
    assert result["maintenance_status"] is None
    assert result["campaign_auto_map_total"] == 0
    assert result["campaign_auto_map_mapped"] == 0
    assert result["commission_files_retried_after_error"] == 0
    assert result["commission_files_retried_after_mapping"] == 0
    assert result["latest_scheduled_backup_at"] is None
    assert result["programs_total"] == 0
    assert result["terms_due_count"] == 0
    assert result["terms_retry_pending"] == 0
    assert result["terms_next_refresh_at"] is None
    assert result["terms_next_scheduled_refresh_at"] is None


def test_ads_folder_error_is_visible_as_runtime_attention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(
        runtime_status_module,
        "google_ads_readiness",
        lambda _db: {
            "status": "CREDENTIALS_REQUIRED",
            "customer_ids": ["1234567890"],
            "customer_count": 1,
            "missing_credentials": ["Developer Token"],
            "login_customer_id_configured": False,
            "write_operations_enabled": False,
        },
    )
    with SessionLocal() as db:
        db.add_all(
            [
                AdsAccount(
                    external_id="123-456-7890",
                    name="Google Ads",
                    currency="VND",
                ),
                SyncRun(
                    connector="AFI_OS_MAINTENANCE",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={},
                ),
                SyncRun(
                    connector="GOOGLE_ADS_FOLDER",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.PARTIAL,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "files_seen": 1,
                        "files_content_detected": 1,
                        "files_duplicate_skipped": 1,
                        "files_account_mismatch": 1,
                        "files_missing_columns": 1,
                        "files_retried_after_error": 1,
                        "files_retried_after_mapping": 1,
                        "error_count": 1,
                        "file_results": [{"rows_read": 9}],
                        "confirmed_file_results": [
                            {
                                "filename": "Báo cáo chiến dịch.csv",
                                "sha256": "a" * 64,
                                "status": "UP_TO_DATE",
                                "checked_at": (
                                    now - timedelta(hours=1)
                                ).isoformat(),
                                "rows_read": 9,
                                "metric_date_to": "2026-08-10",
                                "campaign_id_resolution": {
                                    "resolved_rows": 1,
                                },
                            }
                        ],
                        "last_confirmed_at": (
                            now - timedelta(hours=1)
                        ).isoformat(),
                    },
                ),
            ]
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [
                {
                    "name": "scheduled-runtime-fresh",
                    "created_at": (now - timedelta(hours=1)).isoformat(),
                    "size_bytes": 123,
                    "database_status": "OK",
                }
            ],
        )
    assert result["status"] == "ATTENTION"
    assert result["ads_import_status"] == "PARTIAL"
    assert result["ads_files_seen"] == 1
    assert result["ads_files_content_detected"] == 1
    assert result["ads_files_duplicate_skipped"] == 1
    assert result["ads_files_account_mismatch"] == 1
    assert result["ads_files_missing_columns"] == 1
    assert result["ads_confirmed_file_count"] == 1
    assert result["ads_last_confirmed_at"] == now - timedelta(hours=1)
    assert result["ads_files_retried_after_error"] == 1
    assert result["ads_files_retried_after_mapping"] == 1
    assert result["ads_rows_read"] == 9
    assert result["ads_campaign_ids_recovered"] == 1
    assert result["ads_error_count"] == 1
    assert result["google_ads_customer_ids"] == ["1234567890"]
    assert result["google_ads_login_customer_id_configured"] is False


def test_runtime_prefers_deduplicated_confirmed_ads_row_count() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="GOOGLE_ADS_FOLDER",
                started_at=now - timedelta(minutes=5),
                ended_at=now - timedelta(minutes=4),
                status=SyncStatus.SUCCESS,
                rows_read=18,
                rows_written=0,
                metadata_json={
                    "confirmed_rows_read": 9,
                    "confirmed_file_results": [
                        {
                            "filename": "Báo cáo chiến dịch.csv",
                            "sha256": "a" * 64,
                            "status": "UP_TO_DATE",
                            "rows_read": 9,
                            "metric_date_to": "2026-08-10",
                        },
                        {
                            "filename": "renamed export.csv",
                            "sha256": "b" * 64,
                            "status": "UP_TO_DATE",
                            "rows_read": 9,
                            "metric_date_to": "2026-08-10",
                        },
                    ],
                },
            )
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [],
        )

    assert result["ads_confirmed_file_count"] == 2
    assert result["ads_rows_read"] == 9


def test_runtime_preserves_confirmed_ads_metrics_when_latest_scan_is_empty() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    confirmed_at = now - timedelta(hours=2)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector="AFI_OS_MAINTENANCE",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={},
                ),
                SyncRun(
                    connector="GOOGLE_ADS_FOLDER",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "files_seen": 0,
                        "file_results": [],
                        "confirmed_file_count": 1,
                        "confirmed_file_results": [
                            {
                                "filename": "Báo cáo chiến dịch.csv",
                                "sha256": "b" * 64,
                                "status": "UP_TO_DATE",
                                "checked_at": confirmed_at.isoformat(),
                                "rows_read": 9,
                                "metric_date_from": "2026-08-02",
                                "metric_date_to": "2026-08-10",
                            }
                        ],
                        "last_confirmed_at": confirmed_at.isoformat(),
                        "error_count": 0,
                    },
                ),
            ]
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [
                {
                    "name": "scheduled-confirmed-empty",
                    "created_at": (now - timedelta(hours=1)).isoformat(),
                    "size_bytes": 123,
                    "database_status": "OK",
                }
            ],
        )

    assert result["status"] == "HEALTHY"
    assert result["ads_files_seen"] == 0
    assert result["ads_confirmed_file_count"] == 1
    assert result["ads_last_confirmed_at"] == confirmed_at
    assert result["ads_rows_read"] == 9
    assert result["ads_latest_metric_date"] == date(2026, 8, 10)
    assert result["ads_data_stale"] is False


def test_runtime_status_api_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    payload = {
        "status": "HEALTHY",
        "server_service_loaded": True,
        "maintenance_service_loaded": True,
        "maintenance_status": "SUCCESS",
        "maintenance_last_started_at": now,
        "maintenance_last_ended_at": now,
        "maintenance_next_due_at": now + timedelta(minutes=30),
        "maintenance_overdue": False,
        "maintenance_rows_read": 2,
        "maintenance_rows_written": 0,
        "maintenance_error": None,
        "ads_import_status": "SUCCESS",
        "ads_import_last_at": now,
        "ads_files_seen": 1,
        "ads_files_content_detected": 1,
        "ads_files_duplicate_skipped": 1,
        "ads_files_account_mismatch": 1,
        "ads_files_missing_columns": 1,
        "ads_confirmed_file_count": 1,
        "ads_last_confirmed_at": now,
        "ads_files_retried_after_error": 0,
        "ads_files_retried_after_mapping": 0,
        "ads_rows_read": 9,
        "ads_rows_written": 0,
        "ads_campaign_ids_recovered": 1,
        "ads_error_count": 0,
        "ads_latest_metric_date": now.date(),
        "ads_data_stale": False,
        "ads_latest_report_source_at": now - timedelta(hours=1),
        "ads_intraday_refresh_due": False,
        "ads_next_intraday_refresh_at": now + timedelta(hours=5),
        "commission_import_status": "SUCCESS",
        "commission_import_last_at": now,
        "commission_files_seen": 0,
        "commission_files_retried_after_error": 0,
        "commission_files_retried_after_mapping": 0,
        "commission_rows_read": 0,
        "commission_rows_written": 0,
        "commission_error_count": 0,
        "commission_mapping_required_count": 0,
        "google_ads_api_status": "CREDENTIALS_REQUIRED",
        "google_ads_customer_ids": ["1234567890"],
        "google_ads_api_customer_count": 1,
        "google_ads_api_missing_credentials": ["Developer Token"],
        "google_ads_api_write_operations_enabled": False,
        "latest_scheduled_backup_name": "scheduled-test",
        "latest_scheduled_backup_at": now,
        "latest_scheduled_backup_size_bytes": 123,
        "next_backup_due_at": now + timedelta(hours=24),
        "programs_total": 2,
        "terms_fresh": 2,
        "terms_stale": 0,
        "terms_due_count": 0,
        "terms_retry_pending": 0,
        "terms_next_refresh_at": now + timedelta(hours=23),
        "terms_next_scheduled_refresh_at": now + timedelta(hours=23),
        "programs_terms_ok": 0,
        "programs_terms_warnings": 2,
    }
    monkeypatch.setattr(operations_api, "runtime_status", lambda _db: payload)
    response = client.get("/api/operations/runtime-status")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"
    assert response.json()["ads_files_content_detected"] == 1
    assert response.json()["ads_files_duplicate_skipped"] == 1
    assert response.json()["ads_files_account_mismatch"] == 1
    assert response.json()["ads_files_missing_columns"] == 1
    assert response.json()["ads_confirmed_file_count"] == 1
    assert response.json()["ads_campaign_ids_recovered"] == 1
    assert response.json()["ads_last_confirmed_at"] == "2026-08-11T03:00:00Z"
    assert response.json()["ads_latest_report_source_at"] == "2026-08-11T02:00:00Z"
    assert response.json()["ads_intraday_refresh_due"] is False
    assert response.json()["ads_next_intraday_refresh_at"] == "2026-08-11T08:00:00Z"
    assert response.json()["terms_fresh"] == 2
    assert response.json()["terms_due_count"] == 0
    assert response.json()["terms_retry_pending"] == 0
    assert response.json()["terms_next_refresh_at"] == "2026-08-12T02:00:00Z"
    assert response.json()["terms_next_scheduled_refresh_at"] == "2026-08-12T02:00:00Z"
    assert response.json()["programs_terms_ok"] == 0
    assert response.json()["google_ads_customer_ids"] == ["1234567890"]


def test_runtime_ui_distinguishes_recent_check_from_verified_terms() -> None:
    script = client.get("/app.js")
    assert script.status_code == 200
    assert "Lần rà Terms còn mới" in script.text
    assert "Terms đến hạn gần nhất" in script.text
    assert "Lần rà Terms dự kiến" in script.text
    assert "terms_due_count" in script.text
    assert "terms_retry_pending" in script.text
    assert "terms_next_refresh_at" in script.text
    assert "terms_next_scheduled_refresh_at" in script.text
    assert "Terms đã xác minh" in script.text
    assert "thử lại" in script.text
    assert "MCC đã cấu hình" in script.text
    assert "Manager Customer ID" in script.text
    assert "ads_files_retried_after_error" in script.text
    assert "ads_files_retried_after_mapping" in script.text
    assert "ads_files_content_detected" in script.text
    assert "ads_files_duplicate_skipped" in script.text
    assert "ads_files_account_mismatch" in script.text
    assert "ads_files_missing_columns" in script.text
    assert "ads_confirmed_file_count" in script.text
    assert "ads_last_confirmed_at" in script.text
    assert "ads_latest_report_source_at" in script.text
    assert "ads_intraday_refresh_due" in script.text
    assert "ads_next_intraday_refresh_at" in script.text
    assert "Snapshot Google Ads hôm nay đã hơn 6 giờ" in script.text
    assert "ads_campaign_ids_recovered" in script.text
    assert "tự nhận diện" in script.text
    assert "tự khôi phục" in script.text
    assert "bỏ qua" in script.text
    assert "file sai tài khoản" in script.text
    assert "formatGoogleAdsCustomerId" in script.text
    assert "thiếu cột" in script.text
    assert "xác nhận" in script.text
    assert "commission_files_retried_after_error" in script.text
    assert "commission_files_retried_after_mapping" in script.text
    assert "programs_terms_ok" in script.text
    assert "google_ads_api_next_attempt_at" in script.text
    assert "refreshed_terms_evidence" in script.text
    assert "refreshed_commission_facts" in script.text
    assert "duplicate_terms_evidence" in script.text
    assert "duplicate_commission_facts" in script.text
    assert "làm mới" in script.text


def test_commission_mapping_required_is_runtime_attention() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector="AFI_OS_MAINTENANCE",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={},
                ),
                SyncRun(
                    connector="AFFILIATE_COMMISSION_FOLDER",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.PARTIAL,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "files_seen": 1,
                        "error_count": 0,
                        "mapping_required_count": 1,
                        "file_results": [
                            {
                                "status": "MAPPING_REQUIRED",
                                "rows_read": 0,
                            }
                        ],
                    },
                ),
            ]
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [
                {
                    "name": "scheduled-commission-fresh",
                    "created_at": (now - timedelta(hours=1)).isoformat(),
                    "size_bytes": 123,
                    "database_status": "OK",
                }
            ],
        )
    assert result["status"] == "ATTENTION"
    assert result["commission_import_status"] == "PARTIAL"
    assert result["commission_files_seen"] == 1
    assert result["commission_mapping_required_count"] == 1


def test_runtime_status_exposes_latest_read_only_api_reconciliation() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="GOOGLE_ADS_API_READ_ONLY",
                started_at=now - timedelta(minutes=5),
                ended_at=now - timedelta(minutes=4),
                status=SyncStatus.SUCCESS,
                rows_read=9,
                rows_written=1,
                metadata_json={
                    "reconciliation_before_commit": {
                        "matched_rows": 8,
                        "different_rows": 1,
                        "new_rows": 0,
                    },
                    "write_operations_enabled": False,
                },
            )
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )
    assert result["google_ads_api_sync_status"] == "SUCCESS"
    assert result["google_ads_api_rows_read"] == 9
    assert result["google_ads_api_rows_written"] == 1
    assert result["google_ads_api_reconciliation_differences"] == 1


def test_runtime_exposes_api_cadence_and_pending_setup_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(
        runtime_status_module,
        "google_ads_readiness",
        lambda _db: {
            "status": "READY",
            "customer_count": 1,
            "missing_credentials": [],
            "write_operations_enabled": False,
        },
    )
    monkeypatch.setattr(
        runtime_status_module,
        "google_ads_api_sync_requested",
        lambda: False,
    )
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="GOOGLE_ADS_API_READ_ONLY",
                started_at=now - timedelta(hours=1, minutes=1),
                ended_at=now - timedelta(hours=1),
                status=SyncStatus.SUCCESS,
                rows_read=9,
                rows_written=0,
                metadata_json={"date_to": "2026-08-10"},
            )
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )
        assert result["google_ads_api_sync_due"] is False
        assert result["google_ads_api_next_attempt_at"] == now + timedelta(hours=5)
        assert result["google_ads_api_sync_request_pending"] is False

        monkeypatch.setattr(
            runtime_status_module,
            "google_ads_api_sync_requested",
            lambda: True,
        )
        forced = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: False,
            backup_lister=lambda: [],
        )
    assert forced["google_ads_api_sync_due"] is True
    assert forced["google_ads_api_next_attempt_at"] == now
    assert forced["google_ads_api_sync_request_pending"] is True


def test_fresh_api_keeps_runtime_healthy_when_csv_fallback_is_stale() -> None:
    now = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector="AFI_OS_MAINTENANCE",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={},
                ),
                SyncRun(
                    connector="GOOGLE_ADS_FOLDER",
                    started_at=now - timedelta(minutes=8),
                    ended_at=now - timedelta(minutes=7),
                    status=SyncStatus.PARTIAL,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "error_count": 1,
                        "files_missing_columns": 1,
                        "file_results": [
                            {"status": "ERROR", "metric_date_to": "2026-08-01"}
                        ],
                    },
                ),
                SyncRun(
                    connector="GOOGLE_ADS_API_READ_ONLY",
                    started_at=now - timedelta(minutes=6),
                    ended_at=now - timedelta(minutes=5),
                    status=SyncStatus.SUCCESS,
                    rows_read=9,
                    rows_written=0,
                    metadata_json={
                        "date_to": "2026-08-10",
                        "reconciliation_before_commit": {"different_rows": 0},
                    },
                ),
            ]
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [
                {
                    "name": "scheduled-api-fresh",
                    "created_at": (now - timedelta(hours=1)).isoformat(),
                    "size_bytes": 123,
                    "database_status": "OK",
                }
            ],
        )
    assert result["status"] == "HEALTHY"
    assert result["ads_error_count"] == 0
    assert result["ads_files_missing_columns"] == 0
    assert result["ads_data_stale"] is False
    assert result["ads_latest_metric_date"] == date(2026, 8, 10)


def test_runtime_marks_old_same_day_csv_as_intraday_attention() -> None:
    now = datetime(2026, 8, 11, 15, 0, tzinfo=UTC)
    source_at = now - timedelta(hours=7)
    with SessionLocal() as db:
        db.add_all(
            [
                SyncRun(
                    connector="AFI_OS_MAINTENANCE",
                    started_at=now - timedelta(minutes=10),
                    ended_at=now - timedelta(minutes=9),
                    status=SyncStatus.SUCCESS,
                    rows_read=1,
                    rows_written=0,
                    metadata_json={},
                ),
                SyncRun(
                    connector="GOOGLE_ADS_FOLDER",
                    started_at=now - timedelta(minutes=8),
                    ended_at=now - timedelta(minutes=7),
                    status=SyncStatus.SUCCESS,
                    rows_read=0,
                    rows_written=0,
                    metadata_json={
                        "error_count": 0,
                        "confirmed_file_results": [
                            {
                                "filename": "google-ads-campaign-report.csv",
                                "sha256": "a" * 64,
                                "status": "UP_TO_DATE",
                                "metric_date_to": "2026-08-11",
                                "source_modified_at": source_at.isoformat(),
                                "rows_read": 4,
                            }
                        ],
                    },
                ),
            ]
        )
        db.commit()
        result = runtime_status(
            db,
            now=now,
            service_checker=lambda _label: True,
            backup_lister=lambda: [
                {
                    "name": "scheduled-intraday-test",
                    "created_at": (now - timedelta(hours=1)).isoformat(),
                    "size_bytes": 123,
                    "database_status": "OK",
                }
            ],
        )

    assert result["status"] == "ATTENTION"
    assert result["ads_latest_metric_date"] == now.date()
    assert result["ads_data_stale"] is False
    assert result["ads_latest_report_source_at"] == source_at
    assert result["ads_intraday_refresh_due"] is True
    assert result["ads_next_intraday_refresh_at"] == source_at + timedelta(hours=6)


def test_launchd_checker_rejects_unknown_labels_without_calling_launchctl() -> None:
    assert SERVER_LABEL != MAINTENANCE_LABEL
    assert launchd_service_loaded("com.example.untrusted") is False
