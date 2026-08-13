from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, AutomationJobStatus, AutomationJobType
from afi_os.models import AuditLog, AutomationJob, Program, TermsResearchRun

DEFAULT_LEASE = timedelta(minutes=10)
MAX_BACKOFF = timedelta(hours=6)
SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _now(value: datetime | None = None) -> datetime:
    return _aware(value or datetime.now(UTC))


def _safe_json(value: Any, *, depth: int = 0) -> Any:
    """Keep queue diagnostics useful without persisting credentials or huge bodies."""

    if depth > 5:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:100]:
            key = str(raw_key)[:120]
            if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
                safe[key] = "[REDACTED]"
            else:
                safe[key] = _safe_json(item, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple, set)):
        return [_safe_json(item, depth=depth + 1) for item in list(value)[:100]]
    return str(value)[:2000]


def _safe_error(exc: Exception) -> tuple[str, str]:
    code = type(exc).__name__.upper()[:120]
    message = " ".join(str(exc).split())[:1000]
    for marker in SENSITIVE_KEY_PARTS:
        if marker in message.lower():
            message = "Sensitive error detail redacted; inspect local service logs."
            break
    return code, message or code


def enqueue_job(
    db: Session,
    job_type: AutomationJobType,
    dedupe_key: str,
    *,
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    max_attempts: int = 5,
    run_after: datetime | None = None,
    created_by: str = "system",
) -> tuple[AutomationJob, bool]:
    normalized_key = dedupe_key.strip()
    if not normalized_key or len(normalized_key) > 255:
        raise ValueError("dedupe_key must contain 1..255 characters")
    if max_attempts < 1 or max_attempts > 20:
        raise ValueError("max_attempts must be between 1 and 20")
    if priority < 0 or priority > 1000:
        raise ValueError("priority must be between 0 and 1000")

    existing = db.scalar(select(AutomationJob).where(AutomationJob.dedupe_key == normalized_key))
    if existing is not None:
        return existing, False

    job = AutomationJob(
        job_type=job_type,
        status=AutomationJobStatus.PENDING,
        dedupe_key=normalized_key,
        priority=priority,
        payload_json=_safe_json(payload or {}),
        result_json={},
        attempts=0,
        max_attempts=max_attempts,
        run_after=_now(run_after),
        created_by=created_by[:120],
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(AutomationJob).where(AutomationJob.dedupe_key == normalized_key)
        )
        if existing is None:
            raise
        return existing, False
    db.refresh(job)
    return job, True


def recover_expired_leases(db: Session, *, now: datetime | None = None) -> int:
    current = _now(now)
    dead = db.execute(
        update(AutomationJob)
        .where(
            AutomationJob.status == AutomationJobStatus.RUNNING,
            AutomationJob.lease_expires_at.is_not(None),
            AutomationJob.lease_expires_at <= current,
            AutomationJob.attempts >= AutomationJob.max_attempts,
        )
        .values(
            status=AutomationJobStatus.DEAD_LETTER,
            run_after=current,
            completed_at=current,
            claimed_at=None,
            lease_expires_at=None,
            lease_token=None,
            worker_id=None,
            last_error_code="LEASE_EXPIRED_MAX_ATTEMPTS",
            last_error_message="Worker lease expired at the maximum attempt count.",
            updated_at=current,
        )
        .execution_options(synchronize_session=False)
    )
    retry = db.execute(
        update(AutomationJob)
        .where(
            AutomationJob.status == AutomationJobStatus.RUNNING,
            AutomationJob.lease_expires_at.is_not(None),
            AutomationJob.lease_expires_at <= current,
            AutomationJob.attempts < AutomationJob.max_attempts,
        )
        .values(
            status=AutomationJobStatus.RETRY_WAIT,
            run_after=current,
            claimed_at=None,
            lease_expires_at=None,
            lease_token=None,
            worker_id=None,
            last_error_code="LEASE_EXPIRED",
            last_error_message="Worker lease expired; job returned to retry queue.",
            updated_at=current,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return int(dead.rowcount or 0) + int(retry.rowcount or 0)


def _claim_candidate(
    db: Session,
    candidate_id: int,
    *,
    worker_id: str,
    now: datetime,
    lease: timedelta,
) -> AutomationJob | None:
    token = uuid4().hex
    claimed = db.execute(
        update(AutomationJob)
        .where(
            AutomationJob.id == candidate_id,
            AutomationJob.status.in_(
                [AutomationJobStatus.PENDING, AutomationJobStatus.RETRY_WAIT]
            ),
            AutomationJob.run_after <= now,
        )
        .values(
            status=AutomationJobStatus.RUNNING,
            attempts=AutomationJob.attempts + 1,
            claimed_at=now,
            lease_expires_at=now + lease,
            lease_token=token,
            worker_id=worker_id[:120],
            completed_at=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if not claimed.rowcount:
        return None
    db.expire_all()
    return db.scalar(
        select(AutomationJob).where(
            AutomationJob.id == candidate_id,
            AutomationJob.lease_token == token,
        )
    )


def claim_job(
    db: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
    lease: timedelta = DEFAULT_LEASE,
    job_types: list[AutomationJobType] | None = None,
) -> AutomationJob | None:
    current = _now(now)
    recover_expired_leases(db, now=current)
    for _ in range(5):
        statement = select(AutomationJob.id).where(
            AutomationJob.status.in_(
                [AutomationJobStatus.PENDING, AutomationJobStatus.RETRY_WAIT]
            ),
            AutomationJob.run_after <= current,
        )
        if job_types:
            statement = statement.where(AutomationJob.job_type.in_(job_types))
        candidate_id = db.scalar(
            statement.order_by(
                AutomationJob.priority.desc(),
                AutomationJob.run_after.asc(),
                AutomationJob.id.asc(),
            ).limit(1)
        )
        if candidate_id is None:
            return None
        claimed = _claim_candidate(
            db,
            candidate_id,
            worker_id=worker_id,
            now=current,
            lease=lease,
        )
        if claimed is not None:
            return claimed
        db.expire_all()
    return None


def claim_job_by_id(
    db: Session,
    job_id: int,
    *,
    worker_id: str,
    now: datetime | None = None,
    lease: timedelta = DEFAULT_LEASE,
) -> AutomationJob | None:
    current = _now(now)
    recover_expired_leases(db, now=current)
    return _claim_candidate(
        db,
        job_id,
        worker_id=worker_id,
        now=current,
        lease=lease,
    )


def complete_job(
    db: Session,
    job_id: int,
    lease_token: str,
    *,
    result: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AutomationJob:
    current = _now(now)
    updated = db.execute(
        update(AutomationJob)
        .where(
            AutomationJob.id == job_id,
            AutomationJob.status == AutomationJobStatus.RUNNING,
            AutomationJob.lease_token == lease_token,
        )
        .values(
            status=AutomationJobStatus.SUCCEEDED,
            result_json=_safe_json(result or {}),
            completed_at=current,
            lease_expires_at=None,
            lease_token=None,
            last_error_code=None,
            last_error_message=None,
            updated_at=current,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if not updated.rowcount:
        raise RuntimeError("job lease is no longer owned by this worker")
    db.expire_all()
    return db.get(AutomationJob, job_id)  # type: ignore[return-value]


def fail_job(
    db: Session,
    job_id: int,
    lease_token: str,
    exc: Exception,
    *,
    now: datetime | None = None,
) -> AutomationJob:
    current = _now(now)
    job = db.scalar(
        select(AutomationJob).where(
            AutomationJob.id == job_id,
            AutomationJob.status == AutomationJobStatus.RUNNING,
            AutomationJob.lease_token == lease_token,
        )
    )
    if job is None:
        raise RuntimeError("job lease is no longer owned by this worker")
    error_code, error_message = _safe_error(exc)
    if job.attempts >= job.max_attempts:
        job.status = AutomationJobStatus.DEAD_LETTER
        job.completed_at = current
        job.run_after = current
    else:
        job.status = AutomationJobStatus.RETRY_WAIT
        delay_seconds = min(300 * (2 ** max(job.attempts - 1, 0)), int(MAX_BACKOFF.total_seconds()))
        job.run_after = current + timedelta(seconds=delay_seconds)
        job.completed_at = None
    job.claimed_at = None
    job.lease_expires_at = None
    job.lease_token = None
    job.worker_id = None
    job.last_error_code = error_code
    job.last_error_message = error_message
    job.updated_at = current
    db.commit()
    db.refresh(job)
    return job


def retry_job(
    db: Session,
    job_id: int,
    *,
    actor: str,
    note: str,
    now: datetime | None = None,
) -> AutomationJob:
    current = _now(now)
    job = db.get(AutomationJob, job_id)
    if job is None:
        raise LookupError("automation job not found")
    if job.status not in {
        AutomationJobStatus.RETRY_WAIT,
        AutomationJobStatus.DEAD_LETTER,
        AutomationJobStatus.CANCELLED,
    }:
        raise ValueError("only retry-wait, dead-letter or cancelled jobs can be retried")
    before = job.status.value
    job.status = AutomationJobStatus.PENDING
    job.attempts = 0
    job.run_after = current
    job.claimed_at = None
    job.lease_expires_at = None
    job.lease_token = None
    job.worker_id = None
    job.completed_at = None
    job.updated_at = current
    db.add(
        AuditLog(
            entity_type="AUTOMATION_JOB",
            entity_id=str(job.id),
            action=AuditAction.UPDATE,
            actor=actor[:120],
            payload_json={
                "before_status": before,
                "after_status": AutomationJobStatus.PENDING.value,
                "note": note[:500],
                "warning_only": True,
                "google_ads_write": False,
            },
        )
    )
    db.commit()
    db.refresh(job)
    return job


def list_jobs(
    db: Session,
    *,
    status: AutomationJobStatus | None = None,
    job_type: AutomationJobType | None = None,
    limit: int = 100,
) -> list[AutomationJob]:
    statement = select(AutomationJob)
    if status is not None:
        statement = statement.where(AutomationJob.status == status)
    if job_type is not None:
        statement = statement.where(AutomationJob.job_type == job_type)
    return list(
        db.scalars(
            statement.order_by(
                AutomationJob.created_at.desc(), AutomationJob.id.desc()
            ).limit(max(1, min(limit, 500)))
        ).all()
    )


def queue_summary(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    current = _now(now)
    jobs = list(db.scalars(select(AutomationJob)).all())
    status_counts = Counter(job.status.value for job in jobs)
    type_counts = Counter(job.job_type.value for job in jobs)
    due_jobs = [
        job
        for job in jobs
        if job.status in {AutomationJobStatus.PENDING, AutomationJobStatus.RETRY_WAIT}
        and _aware(job.run_after) <= current
    ]
    future_jobs = [
        job
        for job in jobs
        if job.status in {AutomationJobStatus.PENDING, AutomationJobStatus.RETRY_WAIT}
    ]
    return {
        "counts_by_status": dict(sorted(status_counts.items())),
        "counts_by_type": dict(sorted(type_counts.items())),
        "total": len(jobs),
        "due": len(due_jobs),
        "running": status_counts[AutomationJobStatus.RUNNING.value],
        "retry_wait": status_counts[AutomationJobStatus.RETRY_WAIT.value],
        "dead_letter": status_counts[AutomationJobStatus.DEAD_LETTER.value],
        "oldest_due_at": (
            min((_aware(job.run_after) for job in due_jobs), default=None).isoformat()
            if due_jobs
            else None
        ),
        "next_due_at": (
            min((_aware(job.run_after) for job in future_jobs), default=None).isoformat()
            if future_jobs
            else None
        ),
    }


def terms_job_dedupe_key(
    db: Session,
    program: Program,
    *,
    due_at: datetime,
) -> str:
    latest_id = db.scalar(
        select(func.max(TermsResearchRun.id)).where(
            TermsResearchRun.domain == program.merchant.website_domain
        )
    )
    marker = str(latest_id) if latest_id is not None else "initial"
    return f"terms-research:{program.id}:{marker}:{_aware(due_at).isoformat()}"


def run_terms_research_job(
    db: Session,
    program: Program,
    *,
    due_at: datetime,
    collector: Callable[[Session, str], dict[str, Any]],
    now: datetime | None = None,
    worker_id: str = "maintenance",
) -> tuple[AutomationJob, dict[str, Any] | None]:
    current = _now(now)
    job, _created = enqueue_job(
        db,
        AutomationJobType.TERMS_RESEARCH,
        terms_job_dedupe_key(db, program, due_at=due_at),
        payload={
            "program_id": program.id,
            "domain": program.merchant.website_domain,
            "permission_write_enabled": False,
            "google_ads_write_enabled": False,
        },
        priority=300,
        max_attempts=5,
        run_after=current,
        created_by="auto-maintenance",
    )
    if job.status == AutomationJobStatus.SUCCEEDED:
        return job, job.result_json
    claimed = claim_job_by_id(db, job.id, worker_id=worker_id, now=current)
    if claimed is None:
        return db.get(AutomationJob, job.id), None  # type: ignore[return-value]
    token = claimed.lease_token
    if not token:
        raise RuntimeError("claimed job has no lease token")
    try:
        result = collector(db, program.merchant.website_domain)
    except Exception as exc:
        db.rollback()
        fail_job(db, claimed.id, token, exc, now=current)
        raise
    safe_result = {
        "status": result["run"].status.value,
        "imported_terms_evidence": int(result.get("imported_evidence", 0)),
        "imported_commission_facts": int(result.get("imported", 0)),
        "permissions_changed": False,
        "google_ads_write": False,
    }
    completed = complete_job(db, claimed.id, token, result=safe_result, now=current)
    return completed, result
