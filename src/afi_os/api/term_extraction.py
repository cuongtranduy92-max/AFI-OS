from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from afi_os.db import get_db
from afi_os.enums import AuditAction
from afi_os.models import AuditLog, CommercialProposal, Offer, Program
from afi_os.schemas import (
    CommercialProposalReviewResponse,
    EvidenceReviewRequest,
    ManualPackageCreate,
    ProjectCheckCommission,
    ProjectCheckEvidence,
    ProjectStepOneResponse,
    ProjectTermsExtractionResponse,
)
from afi_os.services.commercial_review import review_commercial_proposal
from afi_os.services.llm_terms import LLMExtractionError, extract_terms_from_pages
from afi_os.services.portfolio import load_portfolio_project
from afi_os.services.project_check import build_project_step_one
from afi_os.services.terms_research import collect_domain_proposal

router = APIRouter(prefix="/api/projects", tags=["term-extraction"])


@router.post("/{project_id}/manual-packages", response_model=ProjectStepOneResponse)
def save_manual_package(
    project_id: int,
    payload: ManualPackageCreate,
    db: Session = Depends(get_db),
) -> ProjectStepOneResponse:
    project = load_portfolio_project(db, project_id)
    if project is None or project.program_id is None:
        raise HTTPException(status_code=404, detail="Project/program not found")
    external_id = f"manual:{payload.name.strip().lower()}"
    offer = db.scalar(
        select(Offer).where(
            Offer.program_id == project.program_id,
            Offer.external_id == external_id,
        )
    )
    if offer is None:
        offer = Offer(program_id=project.program_id, external_id=external_id)
    offer.name = payload.name.strip()
    offer.price = payload.price_usd
    offer.currency = "USD"
    offer.active = True
    offer.source_url = payload.source_url
    offer.notes = (
        f"Operator-entered pricing by {payload.actor}; "
        + ("source URL supplied." if payload.source_url else "official pricing page unavailable.")
    )
    db.add(offer)
    db.flush()
    db.add(
        AuditLog(
            entity_type="offer",
            entity_id=str(offer.id),
            action=AuditAction.UPDATE,
            actor=payload.actor,
            payload_json={
                "name": offer.name,
                "price_usd": str(offer.price),
                "source_url": offer.source_url,
                "manual": True,
                "note": "Giá gói nhập tay vì trang pricing bị chặn hoặc không công khai.",
            },
        )
    )
    db.commit()
    db.expire_all()
    refreshed = load_portfolio_project(db, project_id)
    assert refreshed is not None
    return build_project_step_one(refreshed)


def _commission(item) -> ProjectCheckCommission:  # type: ignore[no-untyped-def]
    return ProjectCheckCommission(
        commission_fact_id=item.id,
        commission_type=item.commission_type,
        commission_rate=item.commission_rate,
        commission_flat=item.commission_flat,
        recurring_months=item.recurring_months,
        rate_is_maximum=item.rate_is_maximum,
        applies_to=item.applies_to,
        review_status=item.review_status,
        excerpt=item.excerpt,
        summary_vi=item.summary_vi,
        quote_vi=item.quote_vi,
        source_url=item.source_url,
        source_authority=item.source_authority,
        checked_at=item.checked_at,
        confidence=item.confidence,
    )


def _evidence(item) -> ProjectCheckEvidence:  # type: ignore[no-untyped-def]
    return ProjectCheckEvidence(
        evidence_id=item.id,
        scope=item.scope,
        decision=item.decision,
        review_status=item.review_status,
        excerpt=item.excerpt,
        summary_vi=item.summary_vi,
        quote_vi=item.quote_vi,
        source_url=item.source_url,
        source_authority=item.source_authority,
        checked_at=item.checked_at,
        confidence=item.confidence,
    )


@router.post("/{project_id}/extract-terms", response_model=ProjectTermsExtractionResponse)
def extract_project_terms(
    project_id: int,
    db: Session = Depends(get_db),
) -> ProjectTermsExtractionResponse:
    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    research = collect_domain_proposal(db, project.domain)
    pages = research.get("pages") or []
    project = load_portfolio_project(db, project_id) or project
    try:
        result = extract_terms_from_pages(db, project, pages)
    except LLMExtractionError as exc:
        status_code = 424 if exc.status in {"CONNECTION_REQUIRED", "AUTH_FAILED"} else 503
        raise HTTPException(
            status_code=status_code,
            detail={
                "status": exc.status,
                "message": exc.detail,
                "setup_command": (
                    "SETUP-LLM.command" if exc.status == "CONNECTION_REQUIRED" else None
                ),
            },
        ) from exc
    return ProjectTermsExtractionResponse(
        project_id=project_id,
        program_id=project.program_id or research["program"].id,
        status=result["status"],
        cached=result["cached"],
        model=result["model"],
        source_urls=result["source_urls"],
        commission_facts=[_commission(item) for item in result["commission_facts"]],
        terms_evidence=[_evidence(item) for item in result["terms_evidence"]],
        commercial_proposals=result["commercial_proposals"],
        ppc_policy=result.get("ppc_policy"),
        rejected=result["rejected"],
    )


@router.post(
    "/{project_id}/commercial-proposals/{proposal_id}/review",
    response_model=CommercialProposalReviewResponse,
)
def review_project_commercial_proposal(
    project_id: int,
    proposal_id: int,
    payload: EvidenceReviewRequest,
    db: Session = Depends(get_db),
) -> CommercialProposalReviewResponse:
    project = load_portfolio_project(db, project_id)
    if project is None or project.program_id is None:
        raise HTTPException(status_code=404, detail="Project/program not found")
    proposal = db.scalar(
        select(CommercialProposal)
        .options(
            selectinload(CommercialProposal.program).selectinload(Program.merchant)
        )
        .where(
            CommercialProposal.id == proposal_id,
            CommercialProposal.program_id == project.program_id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Commercial proposal not found")
    applied = review_commercial_proposal(
        db,
        project,
        proposal,
        action=payload.action,
        reviewed_by=payload.reviewed_by,
    )
    refreshed = load_portfolio_project(db, project_id)
    assert refreshed is not None
    return CommercialProposalReviewResponse(
        proposal=proposal,
        applied_fields=applied,
        step_one=build_project_step_one(refreshed),
    )
