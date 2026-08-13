from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.enums import (
    AuditAction,
    CommissionType,
    EvidenceReviewStatus,
    PermissionStatus,
)
from afi_os.models import AuditLog, CommissionFact, TermsEvidence

REPAIR_VERSION = "truth-semantic-repair-v2"
PREVIOUS_REPAIR_VERSION = "truth-semantic-repair-v1"


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _audit_repair(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    before: dict,
    after: dict,
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=AuditAction.UPDATE,
            actor=REPAIR_VERSION,
            payload_json={
                "before": before,
                "after": after,
                "reason": "Correct a proven scope/cadence parser classification.",
                "warning_only": True,
                "permissions_changed": False,
                "campaign_state_changed": False,
                "google_ads_write": False,
            },
        )
    )


def repair_automated_truth_semantics(db: Session) -> dict[str, int]:
    """Repair known automated parser mis-scopes without accepting any proposal."""

    evidence_scanned = 0
    evidence_repaired = 0
    facts_scanned = 0
    facts_repaired = 0

    evidence_items = list(
        db.scalars(
            select(TermsEvidence).where(
                TermsEvidence.review_status.in_(
                    {EvidenceReviewStatus.PROPOSED, EvidenceReviewStatus.REJECTED}
                ),
                TermsEvidence.collected_by.in_({"AUTOMATED_WEB", "AUTOMATED_FIXTURE"}),
            )
        ).all()
    )
    for evidence in evidence_items:
        evidence_scanned += 1
        text = _compact(evidence.excerpt)
        if not (
            "ppc bidding brand names" in text
            and "without prior written permission" in text
        ):
            continue
        before = {
            "scope": evidence.scope,
            "decision": evidence.decision.value,
            "review_status": evidence.review_status.value,
            "notes": evidence.notes,
        }
        negative_keyword_condition = (
            "negative keyword" in text or "negative keywords" in text
        )
        restored_v1_proposal = (
            evidence.scope == "PAID_SEARCH"
            and evidence.decision == PermissionStatus.NON_BRAND_ONLY
            and evidence.review_status == EvidenceReviewStatus.REJECTED
            and negative_keyword_condition
            and evidence.reviewed_by is None
            and (evidence.notes or "").startswith(PREVIOUS_REPAIR_VERSION)
        )
        if restored_v1_proposal:
            evidence.review_status = EvidenceReviewStatus.PROPOSED
            evidence.notes = (
                f"{REPAIR_VERSION}: restored a valid non-brand PPC proposal after the "
                "previous repair rejected it; operator acceptance remains required."
            )
        elif evidence.review_status != EvidenceReviewStatus.PROPOSED:
            continue
        elif (
            evidence.scope == "BRAND_KEYWORD"
            and evidence.decision == PermissionStatus.PROHIBITED
        ):
            evidence.decision = PermissionStatus.APPROVAL_REQUIRED
            evidence.notes = (
                f"{REPAIR_VERSION}: conditional brand-bidding policy was re-scoped; "
                "operator acceptance remains required."
            )
        elif evidence.scope == "TRADEMARK_AD_COPY":
            evidence.review_status = EvidenceReviewStatus.REJECTED
            evidence.notes = (
                f"{REPAIR_VERSION}: conditional brand-bidding policy was re-scoped; "
                "operator acceptance remains required."
            )
        elif (
            evidence.scope == "PAID_SEARCH"
            and evidence.decision
            in {PermissionStatus.PROHIBITED, PermissionStatus.APPROVAL_REQUIRED}
        ):
            evidence.review_status = EvidenceReviewStatus.REJECTED
            evidence.notes = (
                f"{REPAIR_VERSION}: conditional brand-bidding policy was re-scoped; "
                "operator acceptance remains required."
            )
        elif (
            evidence.scope == "PAID_SEARCH"
            and evidence.decision == PermissionStatus.NON_BRAND_ONLY
            and negative_keyword_condition
        ):
            continue
        else:
            continue
        after = {
            "scope": evidence.scope,
            "decision": evidence.decision.value,
            "review_status": evidence.review_status.value,
            "notes": evidence.notes,
        }
        _audit_repair(
            db,
            entity_type="terms_evidence",
            entity_id=evidence.id,
            before=before,
            after=after,
        )
        evidence_repaired += 1

    fact_items = list(
        db.scalars(
            select(CommissionFact).where(
                CommissionFact.review_status == EvidenceReviewStatus.PROPOSED,
                CommissionFact.collected_by.in_({"AUTOMATED_WEB", "AUTOMATED_FIXTURE"}),
            )
        ).all()
    )
    for fact in fact_items:
        facts_scanned += 1
        text = _compact(fact.excerpt)
        desired: tuple[CommissionType, str] | None = None
        if "entire duration" in text and "subscription" in text and "plan purchase" in text:
            desired = (CommissionType.RECURRING_LIFETIME, "PLAN_SUBSCRIPTION")
        elif (
            "linkedin automation" in text
            and "slot" in text
            and "purchase price" in text
        ):
            desired = (CommissionType.ONE_TIME, "LINKEDIN_AUTOMATION_SLOT")
        if desired is None or (fact.commission_type, fact.applies_to) == desired:
            continue
        before = {
            "commission_type": fact.commission_type.value,
            "applies_to": fact.applies_to,
            "review_status": fact.review_status.value,
            "notes": fact.notes,
        }
        fact.commission_type, fact.applies_to = desired
        fact.notes = (
            f"{REPAIR_VERSION}: cadence/product scope corrected; proposal remains unaccepted."
        )
        after = {
            "commission_type": fact.commission_type.value,
            "applies_to": fact.applies_to,
            "review_status": fact.review_status.value,
            "notes": fact.notes,
        }
        _audit_repair(
            db,
            entity_type="commission_fact",
            entity_id=fact.id,
            before=before,
            after=after,
        )
        facts_repaired += 1

    return {
        "evidence_scanned": evidence_scanned,
        "evidence_repaired": evidence_repaired,
        "facts_scanned": facts_scanned,
        "facts_repaired": facts_repaired,
    }
