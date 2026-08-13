from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.models import AppraisalJob
from afi_os.schemas import (
    AppraisalBatchResponse,
    AppraisalJobResponse,
    AppraisalResponse,
    AppraiseBatchRequest,
    AppraiseRequest,
)
from afi_os.services.appraisal_jobs import (
    appraisal_batch_status,
    create_appraisal_batch,
    create_appraisal_job,
    job_response,
    recover_stale_appraisal_jobs,
    refresh_appraisal_job,
    retry_appraisal_source,
)

router = APIRouter(tags=["appraisal"])


@router.post("/api/appraise", response_model=AppraisalResponse, response_model_by_alias=True)
def appraise_project(
    payload: AppraiseRequest,
    db: Session = Depends(get_db),
) -> AppraisalResponse:
    """Return cached/fast facts now and continue independent sources in the background."""

    return create_appraisal_job(db, payload.domain)


@router.get(
    "/api/appraise/jobs/{job_id}",
    response_model=AppraisalJobResponse,
    response_model_by_alias=True,
)
def get_appraisal_job(job_id: int, db: Session = Depends(get_db)) -> AppraisalJobResponse:
    recover_stale_appraisal_jobs(db)
    job = db.get(AppraisalJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job appraisal")
    return job_response(db, job)


@router.post(
    "/api/appraise/jobs/{job_id}/retry/{source_name}",
    response_model=AppraisalJobResponse,
    response_model_by_alias=True,
)
def retry_appraisal_job_source(
    job_id: int,
    source_name: str,
    db: Session = Depends(get_db),
) -> AppraisalJobResponse:
    try:
        return retry_appraisal_source(db, job_id, source_name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/api/appraise/jobs/{job_id}/refresh",
    response_model=AppraisalJobResponse,
    response_model_by_alias=True,
)
def refresh_appraisal(job_id: int, db: Session = Depends(get_db)) -> AppraisalJobResponse:
    try:
        return refresh_appraisal_job(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/appraise/batch",
    response_model=AppraisalBatchResponse,
    response_model_by_alias=True,
)
def appraise_project_batch(
    payload: AppraiseBatchRequest,
    db: Session = Depends(get_db),
) -> AppraisalBatchResponse:
    """Queue up to 50 domains immediately; traffic uses one Apify batch call."""

    return create_appraisal_batch(db, payload.domains)


@router.get(
    "/api/appraise/batches/{batch_id}",
    response_model=AppraisalBatchResponse,
    response_model_by_alias=True,
)
def get_appraisal_batch(
    batch_id: str,
    db: Session = Depends(get_db),
) -> AppraisalBatchResponse:
    try:
        return appraisal_batch_status(db, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
