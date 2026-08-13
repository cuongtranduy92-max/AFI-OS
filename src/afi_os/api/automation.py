from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.enums import AutomationJobStatus, AutomationJobType
from afi_os.schemas import (
    AutomationJobRead,
    AutomationJobRetryRequest,
    AutomationQueueSummary,
)
from afi_os.services.automation_queue import list_jobs, queue_summary, retry_job

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/queue", response_model=list[AutomationJobRead])
def get_queue(
    status: AutomationJobStatus | None = None,
    job_type: AutomationJobType | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AutomationJobRead]:
    return [AutomationJobRead.model_validate(job) for job in list_jobs(
        db, status=status, job_type=job_type, limit=limit
    )]


@router.get("/queue/summary", response_model=AutomationQueueSummary)
def get_queue_summary(db: Session = Depends(get_db)) -> AutomationQueueSummary:
    return AutomationQueueSummary(**queue_summary(db))


@router.post("/queue/{job_id}/retry", response_model=AutomationJobRead)
def retry_queue_job(
    job_id: int,
    payload: AutomationJobRetryRequest,
    db: Session = Depends(get_db),
) -> AutomationJobRead:
    try:
        job = retry_job(
            db,
            job_id,
            actor=payload.actor,
            note=payload.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AutomationJobRead.model_validate(job)
