from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from afi_os.api.portfolio import (
    intake_portfolio_project,
    run_auto_check_portfolio_project,
)
from afi_os.db import get_db
from afi_os.schemas import (
    AppraisalResponse,
    AppraiseBatchRequest,
    AppraiseRequest,
    ProjectIntakeRequest,
)
from afi_os.services.appraisal import build_appraisal_contract
from afi_os.services.portfolio import load_portfolio_project
from afi_os.services.traffic_provider import collect_project_traffic_batch

router = APIRouter(tags=["appraisal"])


@router.post("/api/appraise", response_model=AppraisalResponse, response_model_by_alias=True)
def appraise_project(
    payload: AppraiseRequest,
    db: Session = Depends(get_db),
) -> AppraisalResponse:
    """Collect source-aware facts and return the stable Step 1 engine contract."""

    auto_check = run_auto_check_portfolio_project(
        ProjectIntakeRequest(domain=payload.domain, actor="appraise-contract-v1"),
        db,
    )
    project = load_portfolio_project(db, auto_check.project.id)
    assert project is not None
    return build_appraisal_contract(db, project, auto_check)


@router.post(
    "/api/appraise/batch",
    response_model=list[AppraisalResponse],
    response_model_by_alias=True,
)
def appraise_project_batch(
    payload: AppraiseBatchRequest,
    db: Session = Depends(get_db),
) -> list[AppraisalResponse]:
    """Pre-fetch Apify once, then run the normal source-aware appraisal per domain."""

    projects = []
    for domain in payload.domains:
        intake = intake_portfolio_project(
            ProjectIntakeRequest(domain=domain, actor="appraise-batch-v1"),
            db,
        )
        project = load_portfolio_project(db, intake.project.id)
        assert project is not None
        projects.append(project)

    traffic_by_domain = collect_project_traffic_batch(db, projects)
    # The projects were loaded before the batch snapshots were committed.
    # Expire the identity map so the contracts below include those snapshots
    # immediately instead of waiting for a later request/session.
    db.expire_all()
    responses: list[AppraisalResponse] = []
    for project in projects:
        auto_check = run_auto_check_portfolio_project(
            ProjectIntakeRequest(domain=project.domain, actor="appraise-batch-v1"),
            db,
            traffic_override=traffic_by_domain.get(project.domain),
        )
        loaded = load_portfolio_project(db, auto_check.project.id)
        assert loaded is not None
        responses.append(build_appraisal_contract(db, loaded, auto_check))
    return responses
