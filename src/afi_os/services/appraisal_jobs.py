from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import URLError

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.db import SessionLocal
from afi_os.enums import (
    AppraisalJobStatus,
    AuditAction,
    ProjectStage,
    RegistrationStatus,
    WatchStatus,
)
from afi_os.models import AppraisalJob, AuditLog, Project
from afi_os.schemas import (
    AppraisalBatchResponse,
    AppraisalFieldStatus,
    AppraisalJobResponse,
    AppraisalResponse,
)
from afi_os.services.appraisal import build_appraisal_contract
from afi_os.services.google_ads_keyword_check import (
    cached_keyword_result,
    collect_project_keyword_metrics,
)
from afi_os.services.llm_terms import LLMExtractionError, extract_terms_from_pages
from afi_os.services.portfolio import load_portfolio_project
from afi_os.services.project_sync import ensure_project_for_program
from afi_os.services.terms_research import collect_domain_proposal
from afi_os.services.traffic_provider import (
    _cached_traffic_result,
    collect_project_traffic,
    collect_project_traffic_batch,
)

logger = logging.getLogger(__name__)

APPRAISAL_WORKERS = 4
FAST_KEYWORD_TIMEOUT_S = 2.5
STALE_JOB_MINUTES = 10
EXECUTABLE_SOURCES = ("keyword", "traffic", "terms")
TERMINAL_SOURCE_STATES = {"ready", "pending_source", "blocked", "error"}

_executor = ThreadPoolExecutor(max_workers=APPRAISAL_WORKERS, thread_name_prefix="afi-appraise")
_job_lock = threading.RLock()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _brand_name(domain: str) -> str:
    label = domain.split(".", 1)[0].replace("-", " ").strip()
    return label.title() or domain


def ensure_appraisal_project(db: Session, domain: str) -> Project:
    project = db.scalar(select(Project).where(Project.domain == domain))
    if project is not None:
        return project
    now = _now()
    project = Project(
        domain=domain,
        brand_name=_brand_name(domain),
        affiliate_program_found=False,
        watch_status=WatchStatus.WATCH,
        stage=ProjectStage.INTAKE,
        registration_status=RegistrationStatus.NOT_STARTED,
        next_action="Đang tự động thu thập nguồn cho Bước 1",
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(project)
    db.flush()
    db.add(
        AuditLog(
            entity_type="project_intake",
            entity_id=str(project.id),
            action=AuditAction.CREATE,
            actor="progressive-appraisal-v1",
            payload_json={
                "domain": domain,
                "entry_type": "PROGRESSIVE_APPRAISAL",
                "permissions_changed": False,
                "campaign_state_changed": False,
                "google_ads_write": False,
            },
        )
    )
    db.commit()
    return project


def _source(
    status: str,
    label: str,
    *,
    detail: str | None = None,
    color: str = "grey",
    retryable: bool = False,
    source_urls: list[str] | None = None,
    checked_at: datetime | None = None,
    cache_date: datetime | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "label": label,
        "detail": detail,
        "color": color,
        "retryable": retryable,
        "source_urls": source_urls or [],
        "checked_at": checked_at.isoformat() if checked_at else None,
        "cache_date": cache_date.isoformat() if cache_date else None,
        "duration_ms": duration_ms,
    }


def _latest_metric_date(project: Project, keys: set[str]) -> datetime | None:
    values = [
        item.observed_at for item in project.metric_snapshots if item.metric_key in keys
    ]
    return max(values) if values else None


def _initial_sources(db: Session, project: Project, *, force_refresh: bool) -> dict[str, Any]:
    now = _now()
    loaded = load_portfolio_project(db, project.id) or project
    traffic_cache = None if force_refresh else _cached_traffic_result(db, project, now=now)
    keyword_cache = None if force_refresh else cached_keyword_result(db, project, now=now)
    has_terms = bool(
        loaded.program
        and (
            loaded.program.terms_evidence
            or loaded.program.commission_facts
            or loaded.program.commercial_proposals
        )
    )
    traffic_date = _latest_metric_date(
        loaded, {"website_traffic_monthly", "top_traffic_countries"}
    )
    keyword_date = _latest_metric_date(
        loaded,
        {
            "primary_keyword_search_volume",
            "primary_keyword_bid_low",
            "primary_keyword_bid_high",
        },
    )
    terms_date = (
        max((item.checked_at for item in loaded.program.terms_research_runs), default=None)
        if loaded.program
        else None
    )
    return {
        "keyword": (
            _source(
                "ready",
                "Từ khoá đã có",
                detail="Dùng cache Google Ads Keyword Planner còn hạn 7 ngày.",
                color="green",
                source_urls=list(keyword_cache.get("source_urls", [])),
                checked_at=keyword_date,
                cache_date=keyword_date,
            )
            if keyword_cache
            else _source("loading", "Đang lấy từ khoá…", detail="Giới hạn fast path 2,5 giây.")
        ),
        "traffic": (
            _source(
                "ready",
                "Traffic đã có",
                detail=str(traffic_cache.get("detail")),
                color="green",
                source_urls=list(traffic_cache.get("source_urls", [])),
                checked_at=traffic_date,
                cache_date=traffic_date,
            )
            if traffic_cache
            else _source("loading", "Đang lấy traffic…", detail="Apify chạy ở nền, tối đa 45 giây.")
        ),
        "terms": (
            _source(
                "ready",
                "Điều khoản đã có",
                detail="Dữ kiện có nguồn đã lưu; chỉ là proposal cho tới khi người vận hành duyệt.",
                color="green",
                checked_at=terms_date,
                cache_date=terms_date,
            )
            if has_terms and not force_refresh
            else _source(
                "loading",
                "Đang đọc điều khoản…",
                detail="Crawler và Claude chạy nền; không tự mở quyền PPC.",
            )
        ),
        "advertisers": (
            _source(
                "ready",
                "Nhà quảng cáo đã có",
                detail="Đã có observation có nguồn trong database.",
                color="green",
            )
            if loaded.observations
            else _source(
                "pending_source",
                "Chưa nối nguồn dữ liệu",
                detail="Tính năng sẽ có khi nối minhbach/SerpApi.",
                color="grey",
            )
        ),
        "niche": _source(
            "ready" if loaded.category else "pending_source",
            "Ngành dự án đã có" if loaded.category else "Chưa nối nguồn dữ liệu",
            detail=(
                "Đã lấy ngành dự án từ hồ sơ đã lưu."
                if loaded.category
                else "Chưa có nguồn phân loại ngành đáng tin cậy; dữ liệu vẫn để trống."
            ),
            color="green" if loaded.category else "grey",
        ),
    }


def _update_source(
    job_id: int,
    source_name: str,
    payload: dict[str, Any],
    *,
    mark_started: bool = False,
) -> None:
    with _job_lock, SessionLocal() as db:
        job = db.get(AppraisalJob, job_id)
        if job is None:
            return
        per_source = dict(job.per_source_json or {})
        per_source[source_name] = payload
        job.per_source_json = per_source
        if mark_started and job.started_at is None:
            job.started_at = _now()
        executable_states = {
            str(per_source.get(name, {}).get("status")) for name in EXECUTABLE_SOURCES
        }
        if executable_states <= TERMINAL_SOURCE_STATES:
            job.status = AppraisalJobStatus.DONE
            job.finished_at = _now()
        else:
            job.status = AppraisalJobStatus.RUNNING
        db.commit()


def _result_source(result: dict[str, Any], *, duration_ms: int) -> dict[str, Any]:
    raw = str(result.get("status", "ERROR")).upper()
    detail = str(result.get("detail") or "")
    urls = list(result.get("source_urls") or [])
    checked_at = result.get("checked_at")
    if isinstance(checked_at, str):
        try:
            checked_at = datetime.fromisoformat(checked_at)
        except ValueError:
            checked_at = None
    if raw in {"CACHED", "COLLECTED", "PROPOSAL_READY", "CONFLICT"}:
        label = "Đã có dữ liệu" if raw != "CACHED" else "Đã có dữ liệu cache"
        return _source(
            "ready",
            label,
            detail=detail,
            color="green",
            source_urls=urls,
            checked_at=checked_at or _now(),
            cache_date=checked_at if raw == "CACHED" else None,
            duration_ms=duration_ms,
        )
    if raw in {"NO_DATA", "EMPTY"}:
        return _source(
            "ready",
            "Không tìm thấy dữ liệu",
            detail=detail,
            color="grey",
            source_urls=urls,
            checked_at=_now(),
            retryable=True,
            duration_ms=duration_ms,
        )
    if raw == "CONNECTION_REQUIRED":
        return _source(
            "pending_source",
            "Chưa nối nguồn dữ liệu",
            detail=detail,
            color="grey",
            source_urls=urls,
            retryable=True,
            duration_ms=duration_ms,
        )
    if raw == "ACCESS_REQUIRED":
        short = detail or "Nguồn đã kết nối nhưng chưa cấp đủ quyền truy cập"
        return _source(
            "error",
            f"Lỗi: {short[:140]}",
            detail=detail,
            color="red",
            source_urls=urls,
            retryable=True,
            duration_ms=duration_ms,
        )
    if raw in {"MANUAL_INPUT_REQUIRED", "BLOCKED"}:
        return _source(
            "blocked",
            "Site chặn truy cập hoặc không có trang affiliate công khai — cần đọc tay",
            detail=detail,
            color="yellow",
            source_urls=urls,
            retryable=True,
            duration_ms=duration_ms,
        )
    short = detail or {
        "AUTH_FAILED": "Thông tin xác thực bị từ chối",
        "RATE_LIMITED": "Nguồn đã hết hạn mức tạm thời",
        "RETRY_REQUIRED": "Nguồn tạm thời không truy cập được",
    }.get(raw, "Không lấy được dữ liệu")
    return _source(
        "error",
        f"Lỗi: {short[:140]}",
        detail=detail,
        color="red",
        source_urls=urls,
        retryable=True,
        duration_ms=duration_ms,
    )


def _worker(
    job_id: int,
    source_name: str,
    collector: Callable[[Session, AppraisalJob, Project], dict[str, Any]],
) -> dict[str, Any]:
    started = time.monotonic()
    _update_source(
        job_id,
        source_name,
        _source("loading", f"Đang lấy {source_name}…"),
        mark_started=True,
    )
    try:
        with SessionLocal() as db:
            job = db.get(AppraisalJob, job_id)
            if job is None:
                return {}
            project = db.get(Project, job.project_id)
            if project is None:
                raise RuntimeError("Không tìm thấy hồ sơ dự án")
            result = collector(db, job, project)
        payload = _result_source(
            result,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:  # isolated failure: other sources keep running
        logger.exception("Appraisal source failed job=%s source=%s", job_id, source_name)
        payload = _source(
            "error",
            f"Lỗi: {type(exc).__name__}",
            detail="Nguồn gặp lỗi kỹ thuật; dữ liệu nguồn khác vẫn được giữ nguyên.",
            color="red",
            retryable=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    _update_source(job_id, source_name, payload)
    return payload


def _collect_keyword(db: Session, job: AppraisalJob, project: Project) -> dict[str, Any]:
    return collect_project_keyword_metrics(
        db, project, force_refresh=bool(job.force_refresh)
    )


def _collect_traffic(db: Session, job: AppraisalJob, project: Project) -> dict[str, Any]:
    return collect_project_traffic(db, project, force_refresh=bool(job.force_refresh))


def _collect_terms(db: Session, job: AppraisalJob, project: Project) -> dict[str, Any]:
    try:
        terms = collect_domain_proposal(db, project.domain)
    except (URLError, TimeoutError, ConnectionError, OSError):
        # One bounded retry is allowed only for an actual transient network failure.
        terms = collect_domain_proposal(db, project.domain)
    program = terms.get("program")
    if program is not None:
        ensure_project_for_program(db, program)
        project = db.scalar(select(Project).where(Project.domain == project.domain)) or project
    pages = list(terms.get("pages") or [])
    source_urls = list(terms.get("source_urls") or [])
    if not pages:
        return {
            "status": "MANUAL_INPUT_REQUIRED",
            "detail": "Crawler không đọc được trang affiliate/terms/pricing công khai.",
            "source_urls": source_urls or [f"https://{project.domain}/"],
        }
    loaded = load_portfolio_project(db, project.id) or project
    try:
        llm = extract_terms_from_pages(db, loaded, pages)
    except LLMExtractionError as exc:
        return {
            "status": exc.status,
            "detail": exc.detail,
            "source_urls": source_urls,
        }
    count = (
        len(llm["commission_facts"])
        + len(llm["terms_evidence"])
        + len(llm["commercial_proposals"])
    )
    return {
        "status": str(llm["status"]),
        "detail": (
            f"{count} đề xuất có trích dẫn; "
            f"{'dùng cache theo nội dung.' if llm['cached'] else 'đã trích xuất mới.'} "
            "Chỉ áp dụng sau khi người vận hành xác nhận."
        ),
        "source_urls": list(llm.get("source_urls") or source_urls),
    }


COLLECTORS: dict[str, Callable[[Session, AppraisalJob, Project], dict[str, Any]]] = {
    "keyword": _collect_keyword,
    "traffic": _collect_traffic,
    "terms": _collect_terms,
}


def _submit_source(job_id: int, source_name: str) -> Future:
    return _executor.submit(_worker, job_id, source_name, COLLECTORS[source_name])


def recover_stale_appraisal_jobs(db: Session | None = None) -> int:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        cutoff = _now() - timedelta(minutes=STALE_JOB_MINUTES)
        jobs = list(
            session.scalars(
                select(AppraisalJob).where(
                    AppraisalJob.status == AppraisalJobStatus.RUNNING,
                    AppraisalJob.started_at < cutoff,
                )
            ).all()
        )
        for job in jobs:
            job.status = AppraisalJobStatus.FAILED
            job.finished_at = _now()
            job.last_error = "Job chạy quá 10 phút; có thể thử lại từng nguồn."
            per_source = dict(job.per_source_json or {})
            for name in EXECUTABLE_SOURCES:
                if per_source.get(name, {}).get("status") == "loading":
                    per_source[name] = _source(
                        "error",
                        "Lỗi: quá thời gian 10 phút",
                        detail=job.last_error,
                        color="red",
                        retryable=True,
                    )
            job.per_source_json = per_source
        if jobs:
            session.commit()
        return len(jobs)
    finally:
        if owns_session:
            session.close()


def _field_statuses(job: AppraisalJob) -> dict[str, AppraisalFieldStatus]:
    return {
        name: AppraisalFieldStatus.model_validate(payload)
        for name, payload in (job.per_source_json or {}).items()
    }


def appraisal_for_job(db: Session, job: AppraisalJob) -> AppraisalResponse:
    project = load_portfolio_project(db, job.project_id)
    if project is None:
        raise LookupError("Project not found")
    return build_appraisal_contract(
        db,
        project,
        job_id=job.id,
        job_status=job.status.value,
        field_statuses=_field_statuses(job),
    )


def job_response(db: Session, job: AppraisalJob) -> AppraisalJobResponse:
    sources = job.per_source_json or {}
    done = sum(
        1
        for name in EXECUTABLE_SOURCES
        if sources.get(name, {}).get("status") in TERMINAL_SOURCE_STATES
    )
    return AppraisalJobResponse(
        job_id=job.id,
        domain=job.domain,
        status=job.status.value,
        progress_done=done,
        progress_total=len(EXECUTABLE_SOURCES),
        created_at=job.created_at,
        finished_at=job.finished_at,
        appraisal=appraisal_for_job(db, job),
    )


def create_appraisal_job(
    db: Session,
    domain: str,
    *,
    batch_id: str | None = None,
    force_refresh: bool = False,
    wait_for_keyword: bool = True,
) -> AppraisalResponse:
    recover_stale_appraisal_jobs(db)
    project = ensure_appraisal_project(db, domain)
    job = AppraisalJob(
        project_id=project.id,
        domain=domain,
        status=AppraisalJobStatus.QUEUED,
        per_source_json=_initial_sources(db, project, force_refresh=force_refresh),
        batch_id=batch_id,
        force_refresh=force_refresh,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    futures: dict[str, Future] = {}
    for source_name in EXECUTABLE_SOURCES:
        if job.per_source_json[source_name]["status"] == "loading":
            futures[source_name] = _submit_source(job.id, source_name)
    if futures:
        job.status = AppraisalJobStatus.RUNNING
        job.started_at = _now()
        db.commit()
        if wait_for_keyword and "keyword" in futures:
            try:
                futures["keyword"].result(timeout=FAST_KEYWORD_TIMEOUT_S)
            except TimeoutError:
                pass
    else:
        job.status = AppraisalJobStatus.DONE
        job.finished_at = _now()
        db.commit()
    db.expire_all()
    refreshed = db.get(AppraisalJob, job.id)
    assert refreshed is not None
    return appraisal_for_job(db, refreshed)


def retry_appraisal_source(db: Session, job_id: int, source_name: str) -> AppraisalJobResponse:
    if source_name not in COLLECTORS:
        raise ValueError("Nguồn không hỗ trợ thử lại")
    recover_stale_appraisal_jobs(db)
    job = db.get(AppraisalJob, job_id)
    if job is None:
        raise LookupError("Job not found")
    per_source = dict(job.per_source_json or {})
    per_source[source_name] = _source("loading", f"Đang thử lại {source_name}…")
    job.per_source_json = per_source
    job.status = AppraisalJobStatus.RUNNING
    job.finished_at = None
    job.last_error = None
    db.commit()
    _submit_source(job.id, source_name)
    db.refresh(job)
    return job_response(db, job)


def refresh_appraisal_job(db: Session, job_id: int) -> AppraisalJobResponse:
    job = db.get(AppraisalJob, job_id)
    if job is None:
        raise LookupError("Job not found")
    per_source = dict(job.per_source_json or {})
    for source_name in EXECUTABLE_SOURCES:
        per_source[source_name] = _source("loading", f"Đang làm mới {source_name}…")
    job.per_source_json = per_source
    job.force_refresh = True
    job.status = AppraisalJobStatus.RUNNING
    job.started_at = _now()
    job.finished_at = None
    job.last_error = None
    db.commit()
    for source_name in EXECUTABLE_SOURCES:
        _submit_source(job.id, source_name)
    db.refresh(job)
    return job_response(db, job)


def _batch_traffic_worker(job_ids: list[int]) -> None:
    started = time.monotonic()
    for job_id in job_ids:
        _update_source(
            job_id,
            "traffic",
            _source("loading", "Đang lấy traffic theo mẻ…"),
            mark_started=True,
        )
    try:
        with SessionLocal() as db:
            jobs = list(db.scalars(select(AppraisalJob).where(AppraisalJob.id.in_(job_ids))).all())
            projects = [project for job in jobs if (project := db.get(Project, job.project_id))]
            results = collect_project_traffic_batch(db, projects)
        for job in jobs:
            result = results.get(job.domain) or {
                "status": "NO_DATA",
                "detail": f"Không tìm thấy traffic cho {job.domain}",
                "source_urls": [],
            }
            _update_source(
                job.id,
                "traffic",
                _result_source(result, duration_ms=int((time.monotonic() - started) * 1000)),
            )
    except Exception as exc:
        logger.exception("Appraisal batch traffic failed")
        for job_id in job_ids:
            _update_source(
                job_id,
                "traffic",
                _source(
                    "error",
                    f"Lỗi: {type(exc).__name__}",
                    detail="Không lấy được traffic theo mẻ; có thể thử lại riêng nguồn Traffic.",
                    color="red",
                    retryable=True,
                ),
            )


def create_appraisal_batch(db: Session, domains: list[str]) -> AppraisalBatchResponse:
    recover_stale_appraisal_jobs(db)
    batch_id = str(uuid.uuid4())
    job_ids: list[int] = []
    for domain in domains:
        project = ensure_appraisal_project(db, domain)
        sources = _initial_sources(db, project, force_refresh=False)
        job = AppraisalJob(
            project_id=project.id,
            domain=domain,
            status=AppraisalJobStatus.RUNNING,
            per_source_json=sources,
            batch_id=batch_id,
            started_at=_now(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_ids.append(job.id)

    traffic_jobs = [
        job.id
        for job in db.scalars(select(AppraisalJob).where(AppraisalJob.id.in_(job_ids))).all()
        if job.per_source_json.get("traffic", {}).get("status") == "loading"
    ]
    if traffic_jobs:
        _executor.submit(_batch_traffic_worker, traffic_jobs)
    for job in db.scalars(select(AppraisalJob).where(AppraisalJob.id.in_(job_ids))).all():
        for source_name in ("keyword", "terms"):
            if job.per_source_json.get(source_name, {}).get("status") == "loading":
                _submit_source(job.id, source_name)
        if all(
            job.per_source_json.get(name, {}).get("status") in TERMINAL_SOURCE_STATES
            for name in EXECUTABLE_SOURCES
        ):
            job.status = AppraisalJobStatus.DONE
            job.finished_at = _now()
    db.commit()
    jobs = list(
        db.scalars(
            select(AppraisalJob).where(AppraisalJob.id.in_(job_ids)).order_by(AppraisalJob.id)
        ).all()
    )
    return AppraisalBatchResponse(
        batch_id=batch_id,
        total=len(jobs),
        done=sum(job.status == AppraisalJobStatus.DONE for job in jobs),
        jobs=[appraisal_for_job(db, job) for job in jobs],
    )


def appraisal_batch_status(db: Session, batch_id: str) -> AppraisalBatchResponse:
    recover_stale_appraisal_jobs(db)
    jobs = list(
        db.scalars(
            select(AppraisalJob)
            .where(AppraisalJob.batch_id == batch_id)
            .order_by(AppraisalJob.id)
        ).all()
    )
    if not jobs:
        raise LookupError("Batch not found")
    return AppraisalBatchResponse(
        batch_id=batch_id,
        total=len(jobs),
        done=sum(
            job.status in {AppraisalJobStatus.DONE, AppraisalJobStatus.FAILED}
            for job in jobs
        ),
        jobs=[appraisal_for_job(db, job) for job in jobs],
    )
