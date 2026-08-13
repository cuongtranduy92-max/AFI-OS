from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    AutomationJobStatus,
    AutomationJobType,
    PermissionStatus,
    ProgramStatus,
)
from afi_os.main import app
from afi_os.models import AuditLog, AutomationJob, Merchant, Program
from afi_os.services.automation_queue import (
    claim_job,
    complete_job,
    enqueue_job,
    fail_job,
    queue_summary,
    retry_job,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program() -> int:
    with SessionLocal() as db:
        merchant = Merchant(name="Queue Merchant", website_domain="queue.example.org")
        db.add(merchant)
        db.flush()
        program = Program(
            merchant_id=merchant.id,
            name="Queue Affiliate Program",
            status=ProgramStatus.DISCOVERED,
        )
        db.add(program)
        db.commit()
        return program.id


def test_enqueue_is_idempotent_and_redacts_sensitive_payload() -> None:
    now = datetime(2026, 8, 12, 4, 0, tzinfo=UTC)
    with SessionLocal() as db:
        first, created = enqueue_job(
            db,
            AutomationJobType.TERMS_RESEARCH,
            "terms:queue.example.org:v1",
            payload={
                "domain": "queue.example.org",
                "oauth_token": "must-not-persist",
                "nested": {"client_secret": "also-private"},
            },
            run_after=now,
        )
        second, duplicate_created = enqueue_job(
            db,
            AutomationJobType.TERMS_RESEARCH,
            "terms:queue.example.org:v1",
            payload={"domain": "different.example.org"},
            run_after=now,
        )

        assert created is True
        assert duplicate_created is False
        assert first.id == second.id
        assert first.payload_json["oauth_token"] == "[REDACTED]"
        assert first.payload_json["nested"]["client_secret"] == "[REDACTED]"
        assert first.payload_json["domain"] == "queue.example.org"
        assert db.scalar(select(AutomationJob).where(AutomationJob.id == first.id)) is not None


def test_atomic_claim_has_one_winner_and_stale_lease_cannot_complete() -> None:
    now = datetime(2026, 8, 12, 4, 10, tzinfo=UTC)
    with SessionLocal() as db:
        job, _ = enqueue_job(
            db,
            AutomationJobType.ADS_IMPORT,
            "ads-import:one-winner",
            run_after=now,
        )
        job_id = job.id

    barrier = Barrier(2)

    def attempt(worker: str) -> tuple[int, str] | None:
        with SessionLocal() as db:
            barrier.wait()
            claimed = claim_job(db, worker_id=worker, now=now)
            return (claimed.id, claimed.lease_token or "") if claimed else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["worker-a", "worker-b"]))

    winners = [item for item in results if item is not None]
    assert len(winners) == 1
    assert winners[0][0] == job_id
    with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="lease"):
            complete_job(db, job_id, "stale-token", result={"status": "BAD"}, now=now)
        completed = complete_job(
            db,
            job_id,
            winners[0][1],
            result={"status": "SUCCESS", "refresh_token": "private"},
            now=now,
        )
        assert completed.status == AutomationJobStatus.SUCCEEDED
        assert completed.result_json["refresh_token"] == "[REDACTED]"


def test_failure_backoff_dead_letter_and_operator_retry_are_audited() -> None:
    now = datetime(2026, 8, 12, 4, 20, tzinfo=UTC)
    with SessionLocal() as db:
        job, _ = enqueue_job(
            db,
            AutomationJobType.COMMISSION_IMPORT,
            "commission:dead-letter",
            max_attempts=2,
            run_after=now,
        )
        first = claim_job(db, worker_id="worker", now=now)
        assert first is not None and first.id == job.id and first.lease_token
        waiting = fail_job(
            db,
            first.id,
            first.lease_token,
            RuntimeError("token=must-not-leak"),
            now=now,
        )
        assert waiting.status == AutomationJobStatus.RETRY_WAIT
        assert waiting.run_after.replace(tzinfo=UTC) == now + timedelta(minutes=5)
        assert "must-not-leak" not in (waiting.last_error_message or "")

        second = claim_job(
            db,
            worker_id="worker",
            now=now + timedelta(minutes=5),
        )
        assert second is not None and second.lease_token
        dead = fail_job(
            db,
            second.id,
            second.lease_token,
            ValueError("permanent parse failure"),
            now=now + timedelta(minutes=5),
        )
        assert dead.status == AutomationJobStatus.DEAD_LETTER
        assert queue_summary(db, now=now + timedelta(minutes=5))["dead_letter"] == 1

        retried = retry_job(
            db,
            dead.id,
            actor="Tran",
            note="source mapping has been supplied",
            now=now + timedelta(minutes=6),
        )
        assert retried.status == AutomationJobStatus.PENDING
        assert retried.attempts == 0
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "AUTOMATION_JOB",
                AuditLog.entity_id == str(dead.id),
            )
        )
        assert audit is not None
        assert audit.payload_json["google_ads_write"] is False
        assert audit.payload_json["warning_only"] is True


def test_expired_lease_returns_to_queue_and_can_be_reclaimed() -> None:
    now = datetime(2026, 8, 12, 4, 30, tzinfo=UTC)
    with SessionLocal() as db:
        job, _ = enqueue_job(
            db,
            AutomationJobType.CAMPAIGN_AUTO_MAP,
            "campaign-map:expired",
            max_attempts=2,
            run_after=now,
        )
        first = claim_job(
            db,
            worker_id="crashed-worker",
            now=now,
            lease=timedelta(seconds=1),
        )
        assert first is not None and first.lease_token
        first_token = first.lease_token

        reclaimed = claim_job(
            db,
            worker_id="replacement-worker",
            now=now + timedelta(seconds=2),
        )
        assert reclaimed is not None and reclaimed.id == job.id
        assert reclaimed.lease_token != first_token
        assert reclaimed.attempts == 2
        assert reclaimed.worker_id == "replacement-worker"

        exhausted = claim_job(
            db,
            worker_id="third-worker",
            now=now + timedelta(minutes=11),
        )
        assert exhausted is None
        db.expire_all()
        dead = db.get(AutomationJob, job.id)
        assert dead is not None
        assert dead.status == AutomationJobStatus.DEAD_LETTER


def test_queue_api_lists_summary_and_allows_only_safe_retry_states() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        job, _ = enqueue_job(
            db,
            AutomationJobType.PROJECT_DISCOVERY,
            "project-discovery:api",
            run_after=now,
        )
        job_id = job.id

    summary = client.get("/api/automation/queue/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["due"] == 1
    listing = client.get("/api/automation/queue")
    assert listing.status_code == 200, listing.text
    assert listing.json()[0]["dedupe_key"] == "project-discovery:api"

    conflict = client.post(
        f"/api/automation/queue/{job_id}/retry",
        json={"actor": "Tran", "note": "not failed"},
    )
    assert conflict.status_code == 409


def test_queue_foundation_does_not_change_ppc_or_remote_campaign_state() -> None:
    program_id = _program()
    with SessionLocal() as db:
        enqueue_job(
            db,
            AutomationJobType.ADVERTISER_REFRESH,
            "advertiser-refresh:queue-project",
            payload={"program_id": program_id},
        )
        program = db.get(Program, program_id)
        assert program is not None
        assert program.paid_search_permission == PermissionStatus.NOT_CHECKED
        assert program.brand_keyword_permission == PermissionStatus.NOT_CHECKED
        assert program.non_brand_permission == PermissionStatus.NOT_CHECKED
        assert program.direct_link_permission == PermissionStatus.NOT_CHECKED
