from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from afi_os.db import get_db
from afi_os.models import Program
from afi_os.schemas import ComplianceEvaluateRequest, ComplianceEvaluateResponse
from afi_os.services.compliance import (
    EvidenceSnapshot,
    LaunchGateInput,
    evaluate_launch_gate,
)
from afi_os.services.programs import program_gate_status

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.post("/evaluate", response_model=ComplianceEvaluateResponse)
def evaluate(
    payload: ComplianceEvaluateRequest,
    db: Session = Depends(get_db),
) -> ComplianceEvaluateResponse:
    program = db.scalar(
        select(Program)
        .options(
            selectinload(Program.merchant),
            selectinload(Program.terms_evidence),
            selectinload(Program.terms_research_runs),
        )
        .where(Program.id == payload.program_id)
    )
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")

    evidence = tuple(
        EvidenceSnapshot(
            scope=item.scope,
            decision=item.decision,
            source_url=item.source_url,
            source_authority=item.source_authority,
            review_status=item.review_status,
            checked_at=item.checked_at,
            expires_at=item.expires_at,
            confidence=item.confidence,
        )
        for item in program.terms_evidence
    )
    result = evaluate_launch_gate(
        LaunchGateInput(
            merchant_domain=program.merchant.website_domain,
            paid_search_permission=program.paid_search_permission,
            brand_keyword_permission=program.brand_keyword_permission,
            non_brand_permission=program.non_brand_permission,
            direct_link_permission=program.direct_link_permission,
            trademark_in_ad_copy_permission=program.trademark_in_ad_copy_permission,
            wants_brand_keywords=payload.wants_brand_keywords,
            wants_direct_link=payload.wants_direct_link,
            evidence=evidence,
            max_evidence_age_days=payload.max_evidence_age_days,
        )
    )
    governing_status = program_gate_status(program, list(program.terms_evidence))
    if result.allowed and governing_status != "TERMS_OK":
        return ComplianceEvaluateResponse(
            allowed=False,
            status=governing_status,
            reasons=[
                "The latest Terms research is not consistent with the accepted evidence."
            ],
            project_included=True,
            warning_only=True,
        )
    return ComplianceEvaluateResponse(
        allowed=result.allowed,
        status=result.status,
        reasons=list(result.reasons),
        project_included=result.project_included,
        warning_only=result.warning_only,
    )
