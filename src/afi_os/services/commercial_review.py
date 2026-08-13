from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.enums import AuditAction, DataQuality, EvidenceReviewStatus, SourceAuthority
from afi_os.models import AuditLog, CommercialProposal, MetricSnapshot, Offer, Program, Project
from afi_os.services.programs import AUTHORITATIVE_SOURCES, source_matches_merchant


def _decimal(value) -> Decimal | None:  # type: ignore[no-untyped-def]
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _metric(
    db: Session,
    project: Project,
    proposal: CommercialProposal,
    key: str,
    value,
    unit: str | None = None,
) -> str | None:  # type: ignore[no-untyped-def]
    if value is None:
        return None
    numeric = _decimal(value) if not isinstance(value, (list, dict, str)) else None
    text = (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, (list, dict))
        else str(value)
        if isinstance(value, str)
        else None
    )
    source_hash = hashlib.sha256(
        f"commercial:{proposal.id}:{key}:{value}".encode()
    ).hexdigest()
    existing = db.scalar(
        select(MetricSnapshot).where(MetricSnapshot.source_hash == source_hash)
    )
    if existing is None:
        db.add(
            MetricSnapshot(
                project_id=project.id,
                metric_key=key,
                numeric_value=numeric,
                text_value=text,
                unit=unit,
                quality=DataQuality.OBSERVED,
                source_name="Claude proposal đã được người vận hành xác nhận",
                source_url=proposal.source_url,
                observed_at=datetime.now(UTC),
                confidence=proposal.confidence,
                method_version="llm-terms-reviewed-v1",
                source_hash=source_hash,
                payload_json={
                    "proposal_id": proposal.id,
                    "quote": proposal.excerpt,
                    "reviewed_by": proposal.reviewed_by,
                },
            )
        )
    return key


def _accept_packages(
    db: Session,
    program: Program,
    proposal: CommercialProposal,
) -> list[str]:
    packages = proposal.payload_json.get("packages")
    if not isinstance(packages, list) or not packages:
        raise HTTPException(status_code=422, detail="Proposal gói giá không hợp lệ")
    applied = []
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        price = _decimal(package.get("price_usd"))
        if not isinstance(name, str) or not name.strip() or price is None:
            continue
        external_id = f"llm:{proposal.id}:{index}"
        offer = db.scalar(
            select(Offer).where(
                Offer.program_id == program.id,
                Offer.external_id == external_id,
            )
        )
        if offer is None:
            offer = Offer(
                program_id=program.id,
                external_id=external_id,
                name=name.strip(),
                price=price,
                currency="USD",
                active=True,
                source_url=proposal.source_url,
                notes=(
                    f"Operator accepted Claude proposal #{proposal.id}. "
                    f"Period: {package.get('period') or 'unknown'}."
                ),
            )
            db.add(offer)
        applied.append(f"package:{name.strip()}")
    if not applied:
        raise HTTPException(status_code=422, detail="Proposal không có gói giá sử dụng được")
    return applied


def _accept_payment(
    db: Session,
    project: Project,
    proposal: CommercialProposal,
) -> list[str]:
    payload = proposal.payload_json
    gateways = payload.get("gateways")
    if not isinstance(gateways, list):
        raise HTTPException(status_code=422, detail="Proposal thanh toán không hợp lệ")
    applied = []
    for key, value, unit in (
        ("payout_methods", gateways or None, None),
        ("minimum_payout", payload.get("min_payment_usd"), "USD"),
        ("payout_timing_days", payload.get("clear_days"), "ngày"),
        ("cookie_days", payload.get("cookie_days"), "ngày"),
        ("affiliate_network", payload.get("net_platform"), None),
    ):
        if written := _metric(db, project, proposal, key, value, unit):
            applied.append(written)
    if not applied:
        raise HTTPException(status_code=422, detail="Proposal không có dữ kiện sử dụng được")
    return applied


def review_commercial_proposal(
    db: Session,
    project: Project,
    proposal: CommercialProposal,
    *,
    action: str,
    reviewed_by: str,
) -> list[str]:
    if proposal.review_status != EvidenceReviewStatus.PROPOSED:
        raise HTTPException(status_code=409, detail="Proposal này đã được xử lý")
    if action == "ACCEPT":
        if proposal.confidence < 0.8:
            raise HTTPException(status_code=422, detail="Confidence phải đạt ít nhất 80%")
        if proposal.source_authority not in AUTHORITATIVE_SOURCES:
            raise HTTPException(status_code=422, detail="Nguồn chưa đủ thẩm quyền để xác nhận")
        if (
            proposal.source_authority == SourceAuthority.OFFICIAL
            and not source_matches_merchant(
                proposal.source_url,
                proposal.program.merchant.website_domain,
            )
        ):
            raise HTTPException(status_code=422, detail="Nguồn OFFICIAL không thuộc merchant")
        if proposal.scope == "PACKAGES":
            applied = _accept_packages(db, proposal.program, proposal)
        else:
            applied = _accept_payment(db, project, proposal)
        proposal.review_status = EvidenceReviewStatus.ACCEPTED
        audit_action = AuditAction.APPROVE
    else:
        applied = []
        proposal.review_status = EvidenceReviewStatus.REJECTED
        audit_action = AuditAction.BLOCK
    proposal.reviewed_at = datetime.now(UTC)
    proposal.reviewed_by = re.sub(r"\s+", " ", reviewed_by).strip()
    db.add(
        AuditLog(
            entity_type="commercial_proposal",
            entity_id=str(proposal.id),
            action=audit_action,
            actor=proposal.reviewed_by,
            payload_json={
                "project_id": project.id,
                "program_id": proposal.program_id,
                "scope": proposal.scope,
                "review_status": proposal.review_status.value,
                "applied_fields": applied,
                "permissions_changed": False,
                "campaign_state_changed": False,
                "google_ads_write": False,
            },
        )
    )
    db.commit()
    db.refresh(proposal)
    return applied
