from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.enums import AuditAction, CampPlanStatus
from afi_os.models import AuditLog, CampPlan, Project
from afi_os.schemas import (
    CampPlanDeployRequest,
    CampPlanEligibleProject,
    CampPlanGenerateRequest,
    CampPlanResponse,
)
from afi_os.services.appraisal import build_appraisal_contract
from afi_os.services.camp_generator import generate_camp_plan
from afi_os.services.portfolio import load_portfolio_project, load_portfolio_projects

router = APIRouter(prefix="/api/projects", tags=["camp-plans"])


def _load_project(db: Session, project_id: int) -> Project:
    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy dự án.")
    return project


def _saved_plan(db: Session, project_id: int) -> CampPlan | None:
    return db.scalar(select(CampPlan).where(CampPlan.project_id == project_id))


def _response(project: Project, saved: CampPlan) -> CampPlanResponse:
    issues = list(saved.linter_json or [])
    return CampPlanResponse(
        id=saved.id,
        project_id=project.id,
        domain=project.domain,
        brand_name=project.brand_name,
        signup_url=project.program.signup_url if project.program else None,
        ref_url=saved.ref_url,
        plan=saved.plan_json or {},
        linter=issues,
        status=saved.status,
        has_errors=any(item.get("level") == "error" for item in issues),
        created_at=saved.created_at,
        updated_at=saved.updated_at,
        google_ads_write=False,
    )


def _assert_step_one_pass(db: Session, project: Project) -> None:
    appraisal = build_appraisal_contract(db, project)
    if appraisal.score.pass_ is True:
        return
    reason = (
        "Bước 1 chưa đủ dữ liệu để kết luận ĐẠT."
        if appraisal.score.pass_ is None
        else "Dự án chưa ĐẠT tiêu chí Bước 1."
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": reason,
            "score": appraisal.score.total,
            "score_pass": appraisal.score.pass_,
            "flags": [item.model_dump(mode="json") for item in appraisal.score.flags],
        },
    )


@router.get("/camp-plan/eligible", response_model=list[CampPlanEligibleProject])
def list_camp_plan_eligible_projects(
    db: Session = Depends(get_db),
) -> list[CampPlanEligibleProject]:
    """List only projects whose stored Step 1 facts currently produce PASS=true."""

    eligible: list[CampPlanEligibleProject] = []
    for project in load_portfolio_projects(db):
        appraisal = build_appraisal_contract(db, project)
        if appraisal.score.pass_ is not True:
            continue
        saved = project.camp_plan
        eligible.append(
            CampPlanEligibleProject(
                project_id=project.id,
                domain=project.domain,
                brand_name=project.brand_name,
                signup_url=project.program.signup_url if project.program else None,
                score_total=appraisal.score.total,
                score_pass=True,
                camp_plan_status=saved.status if saved else None,
                ref_url=saved.ref_url if saved else None,
            )
        )
    return eligible


@router.post("/{project_id}/camp-plan/generate", response_model=CampPlanResponse)
def generate_project_camp_plan(
    project_id: int,
    payload: CampPlanGenerateRequest,
    db: Session = Depends(get_db),
) -> CampPlanResponse:
    project = _load_project(db, project_id)
    _assert_step_one_pass(db, project)
    generated = generate_camp_plan(
        domain=project.domain,
        ref_url=payload.ref_url,
        brand_name=project.brand_name,
        existing_plan=(
            payload.existing_plan.model_dump(mode="json")
            if payload.existing_plan is not None
            else None
        ),
    )
    saved = _saved_plan(db, project.id)
    if saved is None:
        saved = CampPlan(project_id=project.id, ref_url=payload.ref_url)
        db.add(saved)
    saved.ref_url = payload.ref_url
    saved.plan_json = generated.as_dict()
    saved.linter_json = generated.issues_dict()
    saved.status = CampPlanStatus.DRAFT
    db.commit()
    db.refresh(saved)
    return _response(project, saved)


@router.get("/{project_id}/camp-plan", response_model=CampPlanResponse)
def get_project_camp_plan(
    project_id: int,
    db: Session = Depends(get_db),
) -> CampPlanResponse:
    project = _load_project(db, project_id)
    saved = _saved_plan(db, project.id)
    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dự án chưa có bộ nội dung Bước 2.",
        )
    return _response(project, saved)


@router.post("/{project_id}/camp-plan/deploy", response_model=CampPlanResponse)
def deploy_project_camp_plan(
    project_id: int,
    payload: CampPlanDeployRequest,
    db: Session = Depends(get_db),
) -> CampPlanResponse:
    project = _load_project(db, project_id)
    _assert_step_one_pass(db, project)
    saved = _saved_plan(db, project.id)
    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hãy sinh và kiểm tra nội dung trước khi triển khai.",
        )

    checked = generate_camp_plan(
        domain=project.domain,
        ref_url=saved.ref_url,
        brand_name=project.brand_name,
        existing_plan=saved.plan_json,
    )
    saved.linter_json = checked.issues_dict()
    errors = [item for item in saved.linter_json if item.get("level") == "error"]
    if errors:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Còn lỗi nội dung; chưa thể triển khai sang Bước 3.",
                "errors": errors,
            },
        )

    saved.status = CampPlanStatus.DEPLOYED
    db.add(
        AuditLog(
            entity_type="camp_plan",
            entity_id=str(saved.id),
            action=AuditAction.APPROVE,
            actor=payload.actor,
            payload_json={
                "project_id": project.id,
                "domain": project.domain,
                "status": CampPlanStatus.DEPLOYED.value,
                "linter_error_count": 0,
                "campaign_state_changed": False,
                "google_ads_write": False,
            },
        )
    )
    db.commit()
    db.refresh(saved)
    return _response(project, saved)
