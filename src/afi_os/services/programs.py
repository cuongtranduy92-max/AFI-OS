from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from afi_os.enums import (
    EvidenceReviewStatus,
    PermissionStatus,
    ResearchStatus,
    SourceAuthority,
    TermsWarningStatus,
)
from afi_os.models import CommissionFact, Program, TermsEvidence, TermsResearchRun

EVIDENCE_MAX_AGE_DAYS = 90
TERMS_REFRESH_INTERVAL = timedelta(hours=24)
TERMS_RETRY_INTERVAL = timedelta(hours=6)
TERMS_SCHEDULE_GRACE = timedelta(minutes=5)
EXPLICIT_PERMISSION_DECISIONS = {
    PermissionStatus.PROHIBITED,
    PermissionStatus.NON_BRAND_ONLY,
    PermissionStatus.BRAND_ALLOWED,
    PermissionStatus.APPROVAL_REQUIRED,
}
AUTHORITATIVE_SOURCES = {
    SourceAuthority.OFFICIAL,
    SourceAuthority.PARTNER_PORTAL,
    SourceAuthority.WRITTEN_CONFIRMATION,
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def research_attempted_at(run: TermsResearchRun) -> datetime:
    """Return the effective attempt time, including an unchanged-result heartbeat."""

    return max(_aware(run.checked_at), _aware(run.updated_at))


def research_refresh_interval(run: TermsResearchRun) -> timedelta:
    """Retry temporary collection failures sooner than stable research results."""

    if run.status == ResearchStatus.RETRY_REQUIRED:
        return TERMS_RETRY_INTERVAL
    return TERMS_REFRESH_INTERVAL


def research_refresh_due_at(run: TermsResearchRun) -> datetime:
    return research_attempted_at(run) + research_refresh_interval(run)


def latest_research_run(
    runs: Iterable[TermsResearchRun],
) -> TermsResearchRun | None:
    """Select the true latest attempt instead of only the newest source date."""

    return max(
        runs,
        key=lambda run: (research_attempted_at(run), run.id or 0),
        default=None,
    )


def latest_research_runs_by_domain(
    runs: Iterable[TermsResearchRun],
) -> dict[str, TermsResearchRun]:
    latest: dict[str, TermsResearchRun] = {}
    for run in runs:
        current = latest.get(run.domain)
        if current is None or (
            research_attempted_at(run), run.id or 0
        ) > (
            research_attempted_at(current), current.id or 0
        ):
            latest[run.domain] = run
    return latest


def evidence_is_fresh(
    item: TermsEvidence,
    max_age_days: int = EVIDENCE_MAX_AGE_DAYS,
    *,
    require_accepted: bool = True,
) -> bool:
    now = datetime.now(UTC)
    if require_accepted and item.review_status != EvidenceReviewStatus.ACCEPTED:
        return False
    if item.confidence < 0.8:
        return False
    if item.source_authority not in AUTHORITATIVE_SOURCES:
        return False
    if _aware(item.checked_at) < now - timedelta(days=max_age_days):
        return False
    if item.expires_at is not None and _aware(item.expires_at) <= now:
        return False
    return True


def has_evidence(
    evidence: list[TermsEvidence],
    scope: str,
    decisions: set[PermissionStatus],
) -> bool:
    return any(
        item.scope == scope and item.decision in decisions and evidence_is_fresh(item)
        for item in evidence
    )


def accepted_decisions_for_scope(
    evidence: list[TermsEvidence], scope: str
) -> set[PermissionStatus]:
    return {
        item.decision
        for item in evidence
        if item.scope == scope
        and item.decision in EXPLICIT_PERMISSION_DECISIONS
        and evidence_is_fresh(item)
    }


def proposed_decisions_for_scope(
    evidence: list[TermsEvidence], scope: str
) -> set[PermissionStatus]:
    """Return fresh authoritative proposals without treating them as permission."""
    return {
        item.decision
        for item in evidence
        if item.scope == scope
        and item.decision in EXPLICIT_PERMISSION_DECISIONS
        and item.review_status == EvidenceReviewStatus.PROPOSED
        and evidence_is_fresh(item, require_accepted=False)
    }


def resolved_permission_for_scope(
    evidence: list[TermsEvidence], scope: str
) -> PermissionStatus:
    decisions = accepted_decisions_for_scope(evidence, scope)
    if not decisions:
        return PermissionStatus.NOT_CHECKED
    if len(decisions) > 1:
        return PermissionStatus.CONFLICT
    return next(iter(decisions))


def latest_research_requires_warning(
    program: Program,
    evidence: list[TermsEvidence],
    *,
    required_scopes: set[str],
) -> bool:
    """Return true when the newest research attempt lost a usable source.

    ``checked_at`` is the original source timestamp while ``updated_at`` is also
    used as the heartbeat for a repeated identical scan. A later human review is
    an intentional override and can therefore restore the evidence-backed state.
    """

    runs = list(program.terms_research_runs)
    if not runs:
        return False

    latest_run = latest_research_run(runs)
    assert latest_run is not None
    accepted_events: list[datetime] = []
    for item in evidence:
        if item.review_status != EvidenceReviewStatus.ACCEPTED:
            continue
        accepted_events.append(_aware(item.checked_at))
        accepted_events.append(_aware(item.updated_at))
        if item.reviewed_at is not None:
            accepted_events.append(_aware(item.reviewed_at))

    if accepted_events and research_attempted_at(latest_run) <= max(accepted_events):
        return False
    if latest_run.status in {
        ResearchStatus.MANUAL_INPUT_REQUIRED,
        ResearchStatus.RETRY_REQUIRED,
    }:
        return True

    latest_decisions: dict[str, set[PermissionStatus]] = {}
    for proposal in latest_run.permission_proposals or []:
        if not isinstance(proposal, dict):
            continue
        try:
            confidence = float(proposal.get("confidence") or 0)
            decision = PermissionStatus(str(proposal.get("decision")))
        except (TypeError, ValueError):
            continue
        if confidence < 0.8:
            continue
        latest_decisions.setdefault(str(proposal.get("scope")), set()).add(decision)

    return any(
        not accepted_decisions_for_scope(evidence, scope).issubset(
            latest_decisions.get(scope, set())
        )
        for scope in required_scopes
    )


def reconcile_program_permissions(
    program: Program,
    evidence: list[TermsEvidence],
    *,
    reviewed_scope: str | None = None,
) -> None:
    """Reconcile reviewed scopes without erasing unrelated legacy decisions.

    A migrated 0.2.0 program may contain operator-entered permission values that have no
    accepted 0.2.1 evidence yet. Reviewing one scope must not silently reset those other
    fields. The launch gate still requires accepted evidence for every permission it uses.
    """

    fields = {
        "PAID_SEARCH": "paid_search_permission",
        "BRAND_KEYWORD": "brand_keyword_permission",
        "NON_BRAND": "non_brand_permission",
        "DIRECT_LINK": "direct_link_permission",
        "TRADEMARK_AD_COPY": "trademark_in_ad_copy_permission",
    }
    scopes = (
        (reviewed_scope,)
        if reviewed_scope is not None
        else tuple(
            scope
            for scope in fields
            if accepted_decisions_for_scope(evidence, scope)
        )
    )
    for scope in scopes:
        field = fields[scope]
        setattr(program, field, resolved_permission_for_scope(evidence, scope))

    accepted_dates = [
        _aware(item.checked_at)
        for item in evidence
        if item.review_status == EvidenceReviewStatus.ACCEPTED
    ]
    if accepted_dates:
        program.last_terms_checked_at = max(accepted_dates)


def program_terms_status(program: Program, evidence: list[TermsEvidence]) -> str:
    """Return a warning classification without excluding the program from analysis."""

    permissions = {
        program.paid_search_permission,
        program.brand_keyword_permission,
        program.non_brand_permission,
        program.direct_link_permission,
        program.trademark_in_ad_copy_permission,
    }
    if PermissionStatus.CONFLICT in permissions:
        return TermsWarningStatus.WARNING_TERMS_CONFLICT.value
    for scope in (
        "PAID_SEARCH",
        "BRAND_KEYWORD",
        "NON_BRAND",
        "DIRECT_LINK",
        "TRADEMARK_AD_COPY",
    ):
        accepted = accepted_decisions_for_scope(evidence, scope)
        proposed = proposed_decisions_for_scope(evidence, scope)
        if len(accepted) > 1 or len(proposed) > 1:
            return TermsWarningStatus.WARNING_TERMS_CONFLICT.value
        if accepted and proposed and not proposed.issubset(accepted):
            return TermsWarningStatus.WARNING_TERMS_CONFLICT.value

    if program.paid_search_permission == PermissionStatus.PROHIBITED:
        return TermsWarningStatus.WARNING_TERMS_PROHIBITED.value

    if program.paid_search_permission == PermissionStatus.APPROVAL_REQUIRED:
        return TermsWarningStatus.WARNING_APPROVAL_REQUIRED.value

    brand_ready = (
        program.paid_search_permission == PermissionStatus.BRAND_ALLOWED
        and program.brand_keyword_permission == PermissionStatus.BRAND_ALLOWED
        and has_evidence(evidence, "PAID_SEARCH", {PermissionStatus.BRAND_ALLOWED})
        and has_evidence(evidence, "BRAND_KEYWORD", {PermissionStatus.BRAND_ALLOWED})
    )
    if brand_ready and not latest_research_requires_warning(
        program,
        evidence,
        required_scopes={"PAID_SEARCH", "BRAND_KEYWORD"},
    ):
        return TermsWarningStatus.TERMS_OK.value

    non_brand_ready = (
        program.paid_search_permission
        in {PermissionStatus.NON_BRAND_ONLY, PermissionStatus.BRAND_ALLOWED}
        and program.non_brand_permission
        in {PermissionStatus.NON_BRAND_ONLY, PermissionStatus.BRAND_ALLOWED}
        and has_evidence(
            evidence,
            "PAID_SEARCH",
            {PermissionStatus.NON_BRAND_ONLY, PermissionStatus.BRAND_ALLOWED},
        )
        and has_evidence(
            evidence,
            "NON_BRAND",
            {PermissionStatus.NON_BRAND_ONLY, PermissionStatus.BRAND_ALLOWED},
        )
    )
    if non_brand_ready and not latest_research_requires_warning(
        program,
        evidence,
        required_scopes={"PAID_SEARCH", "NON_BRAND"},
    ):
        return TermsWarningStatus.TERMS_OK.value

    if (
        program.non_brand_permission == PermissionStatus.PROHIBITED
        and program.brand_keyword_permission == PermissionStatus.PROHIBITED
    ):
        return TermsWarningStatus.WARNING_TERMS_PROHIBITED.value
    if PermissionStatus.APPROVAL_REQUIRED in {
        program.non_brand_permission,
        program.brand_keyword_permission,
    }:
        return TermsWarningStatus.WARNING_APPROVAL_REQUIRED.value
    return TermsWarningStatus.WARNING_TERMS_UNVERIFIED.value


def program_gate_status(program: Program, evidence: list[TermsEvidence]) -> str:
    """Compatibility name retained for 0.2.1 API fields."""

    return program_terms_status(program, evidence)


def program_evidence_is_stale(program: Program) -> bool:
    if program.last_terms_checked_at is None:
        return True
    checked = _aware(program.last_terms_checked_at)
    return checked < datetime.now(UTC) - timedelta(days=EVIDENCE_MAX_AGE_DAYS)


def permission_field_for(scope: str) -> str:
    fields = {
        "PAID_SEARCH": "paid_search_permission",
        "BRAND_KEYWORD": "brand_keyword_permission",
        "NON_BRAND": "non_brand_permission",
        "DIRECT_LINK": "direct_link_permission",
        "TRADEMARK_AD_COPY": "trademark_in_ad_copy_permission",
    }
    return fields[scope]


def source_matches_merchant(source_url: str, merchant_domain: str) -> bool:
    host = (urlsplit(source_url).hostname or "").lower().rstrip(".")
    domain = merchant_domain.lower().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def program_signup_source_authority(
    signup_url: str | None,
    merchant_domain: str,
) -> SourceAuthority | None:
    if not signup_url:
        return None
    if source_matches_merchant(signup_url, merchant_domain):
        return SourceAuthority.OFFICIAL
    return SourceAuthority.PARTNER_PORTAL


def commission_resolution_status(facts: list[CommissionFact]) -> str:
    """Resolve facts by commercial subject, independently of PPC permissions.

    Different rates for different products are a tiered schedule, not a conflict.
    Legacy cadence-only ``applies_to`` values still represent the same core claim,
    preserving conflict detection for sources such as Pictory's one-time vs lifetime copy.
    """

    qualified = [
        fact
        for fact in facts
        if fact.review_status != EvidenceReviewStatus.REJECTED
        and fact.confidence >= 0.8
        and fact.source_authority in AUTHORITATIVE_SOURCES
    ]
    if not qualified:
        return "NOT_CHECKED"

    distinct_addon_scopes = {"LINKEDIN_AUTOMATION_SLOT"}
    signatures_by_subject: dict[
        str, set[tuple[str, str | None, str | None, int | None, bool]]
    ] = {}
    for fact in qualified:
        subject = (
            fact.applies_to
            if fact.applies_to in distinct_addon_scopes
            else "CORE_AFFILIATE_COMMISSION"
        )
        signatures_by_subject.setdefault(subject, set()).add(
            (
                fact.commission_type.value,
                str(fact.commission_rate) if fact.commission_rate is not None else None,
                str(fact.commission_flat) if fact.commission_flat is not None else None,
                fact.recurring_months,
                fact.rate_is_maximum,
            )
        )
    if any(len(signatures) > 1 for signatures in signatures_by_subject.values()):
        return "CONFLICT"
    if all(
        fact.review_status == EvidenceReviewStatus.ACCEPTED for fact in qualified
    ):
        return "RESOLVED"
    return "PROPOSED"
