from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from afi_os.api.portfolio import auto_check_portfolio_project
from afi_os.db import get_db
from afi_os.schemas import (
    AppraisalResponse,
    AppraiseRequest,
    ProjectIntakeRequest,
)
from afi_os.services.appraisal import build_appraisal_contract
from afi_os.services.portfolio import load_portfolio_project

router = APIRouter(tags=["appraisal"])


@router.post("/api/appraise", response_model=AppraisalResponse, response_model_by_alias=True)
def appraise_project(
    payload: AppraiseRequest,
    db: Session = Depends(get_db),
) -> AppraisalResponse:
    """Collect source-aware facts and return the stable Step 1 engine contract."""

    auto_check = auto_check_portfolio_project(
        ProjectIntakeRequest(domain=payload.domain, actor="appraise-contract-v1"),
        db,
    )
    project = load_portfolio_project(db, auto_check.project.id)
    assert project is not None
    return build_appraisal_contract(db, project, auto_check)
