from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from afi_os.db import get_db
from afi_os.enums import (
    AuditAction,
    EvidenceReviewStatus,
    SourceAuthority,
)
from afi_os.models import (
    AffiliateNetwork,
    AuditLog,
    CommissionFact,
    Merchant,
    Program,
    TermsEvidence,
)
from afi_os.schemas import (
    CommissionFactRead,
    CommissionFactReviewResponse,
    DomainResearchRequest,
    DomainResearchResponse,
    EvidenceReviewRequest,
    EvidenceReviewResponse,
    ProgramCreate,
    ProgramRead,
    ProgramUpdate,
    TermsEvidenceCreate,
    TermsEvidenceCreateResponse,
    TermsEvidenceRead,
    TermsResearchAttemptRead,
)
from afi_os.services.evidence_pack import build_program_evidence_pack
from afi_os.services.programs import (
    AUTHORITATIVE_SOURCES,
    EXPLICIT_PERMISSION_DECISIONS,
    commission_resolution_status,
    latest_research_run,
    program_evidence_is_stale,
    program_gate_status,
    program_signup_source_authority,
    reconcile_program_permissions,
    research_attempted_at,
    research_refresh_due_at,
    resolved_permission_for_scope,
    source_matches_merchant,
)
from afi_os.services.project_sync import ensure_project_for_program
from afi_os.services.terms_research import (
    collect_domain_proposal,
    source_authorities_from_audit_payload,
)

router = APIRouter(prefix="/api/programs", tags=["programs"])


def _program_read(program: Program) -> ProgramRead:
    evidence = list(program.terms_evidence)
    facts = list(program.commission_facts)
    latest_run = latest_research_run(program.terms_research_runs)
    last_research_attempted_at = (
        research_attempted_at(latest_run) if latest_run is not None else None
    )
    research_next_due_at = (
        research_refresh_due_at(latest_run) if latest_run is not None else None
    )
    signup_source_authority = program_signup_source_authority(
        program.signup_url,
        program.merchant.website_domain,
    )
    return ProgramRead(
        id=program.id,
        merchant_name=program.merchant.name,
        website_domain=program.merchant.website_domain,
        program_name=program.name,
        network_name=program.network.name if program.network else None,
        signup_url=program.signup_url,
        signup_source_authority=signup_source_authority,
        status=program.status,
        paid_search_permission=program.paid_search_permission,
        brand_keyword_permission=program.brand_keyword_permission,
        non_brand_permission=program.non_brand_permission,
        direct_link_permission=program.direct_link_permission,
        trademark_in_ad_copy_permission=program.trademark_in_ad_copy_permission,
        last_terms_checked_at=program.last_terms_checked_at,
        last_research_attempted_at=last_research_attempted_at,
        research_next_due_at=research_next_due_at,
        research_status=latest_run.status if latest_run is not None else None,
        research_is_fresh=(
            research_next_due_at is not None and research_next_due_at > datetime.now(UTC)
        ),
        permission_evidence_found=bool(evidence),
        evidence_count=len(evidence),
        evidence_proposal_count=sum(
            item.review_status == EvidenceReviewStatus.PROPOSED for item in evidence
        ),
        commission_fact_count=len(facts),
        commission_state=commission_resolution_status(facts),
        gate_status=program_gate_status(program, evidence),
        evidence_is_stale=program_evidence_is_stale(program),
    )


def _load_program(db: Session, program_id: int) -> Program:
    program = db.scalar(
        select(Program)
        .options(
            selectinload(Program.merchant),
            selectinload(Program.network),
            selectinload(Program.terms_evidence),
            selectinload(Program.commission_facts),
            selectinload(Program.terms_research_runs),
        )
        .where(Program.id == program_id)
        .execution_options(populate_existing=True)
    )
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program


def _nonnegative_count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


@router.get("", response_model=list[ProgramRead])
def list_programs(db: Session = Depends(get_db)) -> list[ProgramRead]:
    programs = db.scalars(
        select(Program)
        .options(
            selectinload(Program.merchant),
            selectinload(Program.network),
            selectinload(Program.terms_evidence),
            selectinload(Program.commission_facts),
            selectinload(Program.terms_research_runs),
        )
        .order_by(Program.updated_at.desc(), Program.id.desc())
    ).all()
    return [_program_read(item) for item in programs]


@router.post("/research", response_model=DomainResearchResponse)
def research_domain(
    payload: DomainResearchRequest,
    db: Session = Depends(get_db),
) -> DomainResearchResponse:
    result = collect_domain_proposal(db, payload.domain)
    run = result["run"]
    program = result["program"]
    facts = result["facts"]
    gate_status = (
        program_gate_status(program, list(program.terms_evidence))
        if program is not None
        else "WARNING_TERMS_UNVERIFIED"
    )
    return DomainResearchResponse(
        run_id=run.id,
        domain=run.domain,
        program_id=program.id if program else None,
        status=run.status,
        checked_at=run.checked_at,
        discovery_confidence=run.discovery_confidence,
        source_urls=result.get("source_urls", list(run.source_urls)),
        source_authorities=result.get("source_authorities", {}),
        permission_proposals=list(run.permission_proposals),
        terms_evidence=result.get("evidence", []),
        imported_terms_evidence=result.get("imported_evidence", 0),
        duplicate_terms_evidence=result.get("duplicate_evidence", 0),
        refreshed_terms_evidence=result.get("refreshed_evidence", 0),
        commission_state=result["commission_state"],
        commission_facts=facts,
        imported_commission_facts=result["imported"],
        duplicate_commission_facts=result["duplicates"],
        refreshed_commission_facts=result.get("refreshed", 0),
        gate_status=gate_status,
        summary=run.summary or "",
        duplicate_run=result["duplicate_run"],
        collection_errors=result.get("collection_errors", []),
        source_change_status=result.get("source_change_status", "UNAVAILABLE"),
        source_changes=result.get("source_changes", []),
    )


@router.get(
    "/{program_id}/research-attempts",
    response_model=list[TermsResearchAttemptRead],
)
def list_research_attempts(
    program_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[TermsResearchAttemptRead]:
    program = _load_program(db, program_id)
    runs = {item.id: item for item in program.terms_research_runs}
    if not runs:
        return []
    audits = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "terms_research_run",
            AuditLog.entity_id.in_([str(run_id) for run_id in runs]),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    attempts = []
    for audit in audits:
        run = runs.get(int(audit.entity_id))
        if run is None:
            continue
        payload = audit.payload_json if isinstance(audit.payload_json, dict) else {}
        source_urls = payload.get("source_urls", run.source_urls)
        priority_urls = payload.get("priority_source_urls", [])
        errors = payload.get("collection_errors", [])
        attempts.append(
            TermsResearchAttemptRead(
                audit_id=audit.id,
                run_id=run.id,
                status=run.status,
                source_checked_at=run.checked_at,
                attempted_at=audit.created_at,
                duplicate_run=payload.get("duplicate_run") is True,
                source_urls=source_urls if isinstance(source_urls, list) else [],
                priority_source_urls=(
                    priority_urls if isinstance(priority_urls, list) else []
                ),
                source_authorities=source_authorities_from_audit_payload(payload),
                collection_errors=errors if isinstance(errors, list) else [],
                source_change_status=(
                    payload.get("source_change_status")
                    if isinstance(payload.get("source_change_status"), str)
                    else "UNAVAILABLE"
                ),
                source_changes=(
                    payload.get("source_changes")
                    if isinstance(payload.get("source_changes"), list)
                    else []
                ),
                imported_terms_evidence=_nonnegative_count(
                    payload.get("imported_terms_evidence")
                ),
                duplicate_terms_evidence=_nonnegative_count(
                    payload.get("duplicate_terms_evidence")
                ),
                refreshed_terms_evidence=_nonnegative_count(
                    payload.get("refreshed_terms_evidence")
                ),
                imported_commission_facts=_nonnegative_count(
                    payload.get("imported_commission_facts")
                ),
                duplicate_commission_facts=_nonnegative_count(
                    payload.get("duplicate_commission_facts")
                ),
                refreshed_commission_facts=_nonnegative_count(
                    payload.get("refreshed_commission_facts")
                ),
                permissions_changed=payload.get("permissions_changed") is True,
                actor=audit.actor,
                summary=run.summary or "",
            )
        )
    return attempts


@router.post("", response_model=ProgramRead)
def create_program(payload: ProgramCreate, db: Session = Depends(get_db)) -> ProgramRead:
    merchant = db.scalar(select(Merchant).where(Merchant.website_domain == payload.website_domain))
    if merchant is None:
        merchant = Merchant(
            name=payload.merchant_name.strip(),
            website_domain=payload.website_domain,
            country=payload.merchant_country,
        )
        db.add(merchant)
        db.flush()
    else:
        merchant.name = payload.merchant_name.strip()
        if payload.merchant_country:
            merchant.country = payload.merchant_country

    network = None
    if payload.network_name:
        normalized_network = payload.network_name.strip()
        network = db.scalar(
            select(AffiliateNetwork).where(
                func.lower(AffiliateNetwork.name) == normalized_network.lower()
            )
        )
        if network is None:
            network = AffiliateNetwork(name=normalized_network)
            db.add(network)
            db.flush()

    program = db.scalar(
        select(Program).where(
            Program.merchant_id == merchant.id,
            func.lower(Program.name) == payload.program_name.strip().lower(),
        )
    )
    values = payload.model_dump(
        exclude={
            "merchant_name",
            "website_domain",
            "merchant_country",
            "program_name",
            "network_name",
        },
        exclude_unset=True,
    )
    if program is None:
        program = Program(
            merchant_id=merchant.id,
            network_id=network.id if network else None,
            name=payload.program_name.strip(),
            **values,
        )
        db.add(program)
    else:
        for key, value in values.items():
            setattr(program, key, value)
        if network:
            program.network_id = network.id
    db.flush()
    ensure_project_for_program(db, program, actor="program-api-v1")
    db.commit()
    return _program_read(_load_program(db, program.id))


@router.patch("/{program_id}", response_model=ProgramRead)
def update_program(
    program_id: int,
    payload: ProgramUpdate,
    db: Session = Depends(get_db),
) -> ProgramRead:
    program = _load_program(db, program_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(program, key, value)
    db.commit()
    return _program_read(_load_program(db, program_id))


@router.get("/{program_id}/evidence", response_model=list[TermsEvidenceRead])
def list_evidence(program_id: int, db: Session = Depends(get_db)) -> list[TermsEvidenceRead]:
    _load_program(db, program_id)
    return list(
        db.scalars(
            select(TermsEvidence)
            .where(TermsEvidence.program_id == program_id)
            .order_by(TermsEvidence.checked_at.desc(), TermsEvidence.id.desc())
        ).all()
    )


@router.get("/{program_id}/evidence-pack")
def export_evidence_pack(
    program_id: int,
    db: Session = Depends(get_db),
) -> Response:
    program = _load_program(db, program_id)
    filename, content = build_program_evidence_pack(db, program)
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-AFI-OS-Permissions-Changed": "false",
        },
    )


@router.get("/{program_id}/commission-facts", response_model=list[CommissionFactRead])
def list_commission_facts(
    program_id: int, db: Session = Depends(get_db)
) -> list[CommissionFactRead]:
    _load_program(db, program_id)
    return list(
        db.scalars(
            select(CommissionFact)
            .where(CommissionFact.program_id == program_id)
            .order_by(CommissionFact.checked_at.desc(), CommissionFact.id.desc())
        ).all()
    )


@router.post(
    "/{program_id}/commission-facts/{fact_id}/review",
    response_model=CommissionFactReviewResponse,
)
def review_commission_fact(
    program_id: int,
    fact_id: int,
    payload: EvidenceReviewRequest,
    db: Session = Depends(get_db),
) -> CommissionFactReviewResponse:
    program = _load_program(db, program_id)
    fact = db.scalar(
        select(CommissionFact).where(
            CommissionFact.id == fact_id,
            CommissionFact.program_id == program_id,
        )
    )
    if fact is None:
        raise HTTPException(status_code=404, detail="Commission fact not found")

    if payload.action == "ACCEPT":
        if fact.confidence < 0.8:
            raise HTTPException(
                status_code=422,
                detail="Confidence must be at least 0.8 before a commission fact is accepted.",
            )
        checked_at = fact.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        if checked_at > datetime.now(UTC) + timedelta(minutes=5):
            raise HTTPException(
                status_code=422,
                detail="Commission fact checked_at cannot be in the future.",
            )
        if fact.source_authority not in AUTHORITATIVE_SOURCES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Only official, partner-portal, or written-confirmation facts "
                    "can be accepted."
                ),
            )
        if (
            fact.source_authority == SourceAuthority.OFFICIAL
            and not source_matches_merchant(
                fact.source_url, program.merchant.website_domain
            )
        ):
            raise HTTPException(
                status_code=422,
                detail="An OFFICIAL commission source must belong to the merchant domain.",
            )
        fact.review_status = EvidenceReviewStatus.ACCEPTED
        audit_action = AuditAction.APPROVE
    else:
        fact.review_status = EvidenceReviewStatus.REJECTED
        audit_action = AuditAction.BLOCK

    db.flush()
    db.add(
        AuditLog(
            entity_type="commission_fact",
            entity_id=str(fact.id),
            action=audit_action,
            actor=payload.reviewed_by,
            payload_json={
                "program_id": program_id,
                "review_status": fact.review_status.value,
                "commission_type": fact.commission_type.value,
                "commission_rate": (
                    str(fact.commission_rate)
                    if fact.commission_rate is not None
                    else None
                ),
                "permissions_changed": False,
            },
        )
    )
    db.commit()
    db.refresh(fact)
    facts = list(
        db.scalars(
            select(CommissionFact).where(CommissionFact.program_id == program_id)
        ).all()
    )
    return CommissionFactReviewResponse(
        fact=fact,
        commission_state=commission_resolution_status(facts),
        permissions_changed=False,
    )


def _evidence_digest(program_id: int, payload: TermsEvidenceCreate) -> str:
    excerpt = re.sub(r"\s+", " ", payload.excerpt.strip())
    source_url = payload.source_url.strip().rstrip("/")
    digest_source = "|".join(
        [str(program_id), source_url, payload.scope, payload.decision.value, excerpt]
    )
    return hashlib.sha256(digest_source.encode("utf-8")).hexdigest()


@router.post("/{program_id}/evidence", response_model=TermsEvidenceCreateResponse)
def create_evidence(
    program_id: int,
    payload: TermsEvidenceCreate,
    db: Session = Depends(get_db),
) -> TermsEvidenceCreateResponse:
    program = _load_program(db, program_id)
    evidence_hash = _evidence_digest(program_id, payload)
    existing = db.scalar(
        select(TermsEvidence).where(TermsEvidence.evidence_hash == evidence_hash)
    )
    if existing is not None:
        updated = False
        if existing.review_status != EvidenceReviewStatus.ACCEPTED:
            existing.source_type = payload.source_type
            existing.checked_at = payload.checked_at
            existing.expires_at = payload.expires_at
            existing.reviewer = payload.reviewer
            existing.confidence = payload.confidence
            existing.source_authority = payload.source_authority
            existing.notes = payload.notes
            existing.review_status = EvidenceReviewStatus.PROPOSED
            existing.reviewed_at = None
            existing.reviewed_by = None
            existing.collected_by = "MANUAL"
            db.add(
                AuditLog(
                    entity_type="terms_evidence",
                    entity_id=str(existing.id),
                    action=AuditAction.UPDATE,
                    actor=payload.reviewer,
                    payload_json={
                        "scope": existing.scope,
                        "review_status": EvidenceReviewStatus.PROPOSED.value,
                        "metadata_refreshed": True,
                        "permissions_changed": False,
                    },
                )
            )
            db.commit()
            db.refresh(existing)
            program = _load_program(db, program_id)
            updated = True
        return TermsEvidenceCreateResponse(
            evidence=existing,
            duplicate=True,
            updated=updated,
            proposal_state=existing.review_status,
            program_gate_status=program_gate_status(program, list(program.terms_evidence)),
        )

    values = payload.model_dump()
    scope = values.pop("scope")
    evidence = TermsEvidence(
        program_id=program_id,
        evidence_hash=evidence_hash,
        scope=scope,
        applies_to=scope,
        review_status=EvidenceReviewStatus.PROPOSED,
        collected_by="MANUAL",
        **values,
    )
    db.add(evidence)
    db.flush()
    db.add(
        AuditLog(
            entity_type="terms_evidence",
            entity_id=str(evidence.id),
            action=AuditAction.CREATE,
            actor=payload.reviewer,
            payload_json={
                "scope": scope,
                "decision": payload.decision.value,
                "confidence": payload.confidence,
                "review_status": EvidenceReviewStatus.PROPOSED.value,
                "permissions_changed": False,
            },
        )
    )
    db.commit()
    db.refresh(evidence)
    program = _load_program(db, program_id)
    return TermsEvidenceCreateResponse(
        evidence=evidence,
        duplicate=False,
        proposal_state=evidence.review_status,
        program_gate_status=program_gate_status(program, list(program.terms_evidence)),
    )


@router.post(
    "/{program_id}/evidence/{evidence_id}/review",
    response_model=EvidenceReviewResponse,
)
def review_evidence(
    program_id: int,
    evidence_id: int,
    payload: EvidenceReviewRequest,
    db: Session = Depends(get_db),
) -> EvidenceReviewResponse:
    program = _load_program(db, program_id)
    evidence = db.scalar(
        select(TermsEvidence).where(
            TermsEvidence.id == evidence_id,
            TermsEvidence.program_id == program_id,
        )
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if payload.action == "ACCEPT":
        if evidence.decision not in EXPLICIT_PERMISSION_DECISIONS:
            raise HTTPException(
                status_code=422,
                detail="NOT_CHECKED/AMBIGUOUS/CONFLICT cannot be accepted as explicit permission.",
            )
        if evidence.confidence < 0.8:
            raise HTTPException(
                status_code=422,
                detail="Confidence must be at least 0.8 before evidence can be accepted.",
            )
        checked_at = evidence.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        if checked_at > datetime.now(UTC) + timedelta(minutes=5):
            raise HTTPException(
                status_code=422,
                detail="Evidence checked_at cannot be in the future.",
            )
        if evidence.source_authority not in AUTHORITATIVE_SOURCES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Only official, partner-portal, or written-confirmation evidence "
                    "can be accepted."
                ),
            )
        if (
            evidence.source_authority == SourceAuthority.OFFICIAL
            and not source_matches_merchant(
                evidence.source_url, program.merchant.website_domain
            )
        ):
            raise HTTPException(
                status_code=422,
                detail="An OFFICIAL source URL must belong to the merchant domain.",
            )
        evidence.review_status = EvidenceReviewStatus.ACCEPTED
        audit_action = AuditAction.APPROVE
    else:
        evidence.review_status = EvidenceReviewStatus.REJECTED
        audit_action = AuditAction.BLOCK

    evidence.reviewed_at = datetime.now(UTC)
    evidence.reviewed_by = payload.reviewed_by
    db.flush()
    all_evidence = list(
        db.scalars(select(TermsEvidence).where(TermsEvidence.program_id == program_id)).all()
    )
    reconcile_program_permissions(program, all_evidence, reviewed_scope=evidence.scope)
    resolved = resolved_permission_for_scope(all_evidence, evidence.scope)
    db.add(
        AuditLog(
            entity_type="terms_evidence",
            entity_id=str(evidence.id),
            action=audit_action,
            actor=payload.reviewed_by,
            payload_json={
                "scope": evidence.scope,
                "review_status": evidence.review_status.value,
                "resolved_permission": resolved.value,
            },
        )
    )
    db.commit()
    db.refresh(evidence)
    program = _load_program(db, program_id)
    return EvidenceReviewResponse(
        evidence=evidence,
        resolved_permission=resolved,
        program_gate_status=program_gate_status(program, list(program.terms_evidence)),
    )
