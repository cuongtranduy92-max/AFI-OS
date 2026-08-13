from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AutomationJobStatus, AutomationJobType
from afi_os.models import AutomationJob, Campaign, Program
from afi_os.services.automation_queue import claim_job, enqueue_job, fail_job
from afi_os.services.operations import operations_inbox


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_dead_letter_enters_operations_without_mutating_campaign_or_program() -> None:
    now = datetime(2026, 8, 12, 4, 30, tzinfo=UTC)
    with SessionLocal() as db:
        job, _ = enqueue_job(
            db,
            AutomationJobType.ADS_IMPORT,
            "ads:dead-letter:operations",
            max_attempts=1,
            run_after=now,
        )
        claimed = claim_job(db, worker_id="test", now=now)
        assert claimed is not None and claimed.lease_token
        dead = fail_job(
            db,
            claimed.id,
            claimed.lease_token,
            RuntimeError("developer_token=must-not-leak"),
            now=now,
        )
        assert dead.status == AutomationJobStatus.DEAD_LETTER

        inbox = operations_inbox(db, today=now.date(), now=now)
        item = next(item for item in inbox["items"] if item["item_type"] == "AUTOMATION_DEAD_LETTER")
        assert item["entity_id"] == str(job.id)
        assert item["severity"] == "ACTION"
        assert item["requires_user"] is True
        assert item["action_view"] == "command"
        assert "must-not-leak" not in item["detail"]
        assert "không bị thay đổi" in item["detail"]
        assert db.scalar(select(Campaign).limit(1)) is None
        assert db.scalar(select(Program).limit(1)) is None


def test_retry_wait_does_not_create_operator_exception() -> None:
    now = datetime(2026, 8, 12, 4, 40, tzinfo=UTC)
    with SessionLocal() as db:
        job, _ = enqueue_job(
            db,
            AutomationJobType.TERMS_RESEARCH,
            "terms:retry-wait:operations",
            max_attempts=2,
            run_after=now,
        )
        claimed = claim_job(db, worker_id="test", now=now)
        assert claimed is not None and claimed.lease_token
        waiting = fail_job(db, job.id, claimed.lease_token, RuntimeError("temporary"), now=now)
        assert waiting.status == AutomationJobStatus.RETRY_WAIT
        inbox = operations_inbox(db, today=now.date(), now=now)
        assert not any(item["item_type"] == "AUTOMATION_DEAD_LETTER" for item in inbox["items"])


def test_operations_button_targets_exact_queue_row() -> None:
    script = open("apps/web/app.js", encoding="utf-8").read()
    assert script.count('data-automation-job-row="${job.id}"') == 1
    portfolio_block = script.split("async function loadPortfolio()", 1)[1].split(
        "function openTruthDrawer", 1
    )[0]
    operations_block = script.split("async function loadOperations()", 1)[1].split(
        "const automationJobLabels", 1
    )[0]
    queue_block = script.split("async function loadAutomationQueue()", 1)[1].split(
        "async function retryAutomationJob", 1
    )[0]
    assert 'data-automation-job-row="${job.id}"' not in portfolio_block
    assert "job.id" not in operations_block
    assert 'data-automation-job-row="${job.id}"' in queue_block
    assert 'function focusAutomationJobTarget(jobId)' in script
    assert 'itemType === "AUTOMATION_DEAD_LETTER"' in script
    assert 'focusAutomationJobTarget(entityId)' in script
