from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from afi_os.enums import EvidenceReviewStatus, PermissionStatus, SourceAuthority

AUTHORITATIVE_SOURCES = {
    SourceAuthority.OFFICIAL,
    SourceAuthority.PARTNER_PORTAL,
    SourceAuthority.WRITTEN_CONFIRMATION,
}
EXPLICIT_DECISIONS = {
    PermissionStatus.PROHIBITED,
    PermissionStatus.NON_BRAND_ONLY,
    PermissionStatus.BRAND_ALLOWED,
    PermissionStatus.APPROVAL_REQUIRED,
}


@dataclass(frozen=True)
class EvidenceSnapshot:
    scope: str
    decision: PermissionStatus
    source_url: str
    source_authority: SourceAuthority
    review_status: EvidenceReviewStatus
    checked_at: datetime
    expires_at: datetime | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class LaunchGateInput:
    merchant_domain: str
    paid_search_permission: PermissionStatus
    brand_keyword_permission: PermissionStatus
    non_brand_permission: PermissionStatus
    direct_link_permission: PermissionStatus
    wants_brand_keywords: bool
    wants_direct_link: bool
    trademark_in_ad_copy_permission: PermissionStatus = PermissionStatus.NOT_CHECKED
    evidence: tuple[EvidenceSnapshot, ...] = ()
    max_evidence_age_days: int = 90


@dataclass(frozen=True)
class LaunchGateResult:
    allowed: bool
    status: str
    reasons: tuple[str, ...]
    project_included: bool = True
    warning_only: bool = True


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _official_source_matches_merchant(source_url: str, merchant_domain: str) -> bool:
    host = (urlsplit(source_url).hostname or "").lower().rstrip(".")
    domain = merchant_domain.lower().rstrip(".")
    return bool(host) and (host == domain or host.endswith(f".{domain}"))


def _is_qualified_evidence(
    data: LaunchGateInput,
    item: EvidenceSnapshot,
    *,
    now: datetime,
) -> bool:
    checked = _aware(item.checked_at)
    oldest = now - timedelta(days=data.max_evidence_age_days)
    if item.review_status != EvidenceReviewStatus.ACCEPTED:
        return False
    if item.source_authority not in AUTHORITATIVE_SOURCES:
        return False
    if item.confidence < 0.8 or checked < oldest or checked > now + timedelta(minutes=5):
        return False
    if item.expires_at is not None and _aware(item.expires_at) <= now:
        return False
    parsed = urlsplit(item.source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if item.source_authority == SourceAuthority.OFFICIAL and not _official_source_matches_merchant(
        item.source_url, data.merchant_domain
    ):
        return False
    return True


def _has_fresh_explicit_evidence(
    data: LaunchGateInput,
    scope: str,
    desired: PermissionStatus,
) -> bool:
    now = datetime.now(UTC)
    return any(
        item.scope == scope
        and item.decision == desired
        and _is_qualified_evidence(data, item, now=now)
        for item in data.evidence
    )


def _scope_has_conflict(data: LaunchGateInput, scope: str) -> bool:
    now = datetime.now(UTC)
    decisions = {
        item.decision
        for item in data.evidence
        if item.scope == scope
        and item.decision in EXPLICIT_DECISIONS
        and _is_qualified_evidence(data, item, now=now)
    }
    return len(decisions) > 1


def evaluate_launch_gate(data: LaunchGateInput) -> LaunchGateResult:
    reasons: list[str] = []

    permission_values = {
        data.paid_search_permission,
        data.brand_keyword_permission,
        data.non_brand_permission,
        data.direct_link_permission,
        data.trademark_in_ad_copy_permission,
    }
    relevant_scopes = {"PAID_SEARCH", "BRAND_KEYWORD", "NON_BRAND", "DIRECT_LINK"}
    if PermissionStatus.CONFLICT in permission_values or any(
        _scope_has_conflict(data, scope) for scope in relevant_scopes
    ):
        return LaunchGateResult(
            False,
            "WARNING_TERMS_CONFLICT",
            ("Accepted authoritative evidence contains a permission conflict.",),
        )

    if data.paid_search_permission == PermissionStatus.PROHIBITED:
        reasons.append("Paid search is explicitly prohibited.")

    if data.paid_search_permission in {
        PermissionStatus.NOT_CHECKED,
        PermissionStatus.AMBIGUOUS,
        PermissionStatus.APPROVAL_REQUIRED,
        PermissionStatus.CONFLICT,
    }:
        reasons.append("Paid-search permission is not explicitly proven.")
    elif data.paid_search_permission in {
        PermissionStatus.NON_BRAND_ONLY,
        PermissionStatus.BRAND_ALLOWED,
    } and not _has_fresh_explicit_evidence(
        data,
        "PAID_SEARCH",
        data.paid_search_permission,
    ):
        reasons.append("Paid search lacks accepted, sourced, authoritative evidence.")

    if data.wants_brand_keywords:
        if data.paid_search_permission != PermissionStatus.BRAND_ALLOWED:
            reasons.append("Brand bidding requires paid search to be explicitly brand-allowed.")
        if data.brand_keyword_permission != PermissionStatus.BRAND_ALLOWED:
            reasons.append("Brand keyword bidding is not explicitly allowed.")
        elif not _has_fresh_explicit_evidence(
            data,
            "BRAND_KEYWORD",
            PermissionStatus.BRAND_ALLOWED,
        ):
            reasons.append("Brand bidding lacks accepted, sourced, authoritative evidence.")
    else:
        if data.non_brand_permission not in {
            PermissionStatus.NON_BRAND_ONLY,
            PermissionStatus.BRAND_ALLOWED,
        }:
            reasons.append("Non-brand paid search is not explicitly allowed.")
        elif not _has_fresh_explicit_evidence(
            data,
            "NON_BRAND",
            data.non_brand_permission,
        ):
            reasons.append("Non-brand search lacks accepted, sourced, authoritative evidence.")

    if data.wants_direct_link:
        if data.direct_link_permission != PermissionStatus.BRAND_ALLOWED:
            reasons.append("Direct linking is not explicitly allowed.")
        elif not _has_fresh_explicit_evidence(
            data,
            "DIRECT_LINK",
            PermissionStatus.BRAND_ALLOWED,
        ):
            reasons.append("Direct linking lacks accepted, sourced, authoritative evidence.")

    if reasons:
        if data.paid_search_permission == PermissionStatus.PROHIBITED:
            status = "WARNING_TERMS_PROHIBITED"
        elif data.paid_search_permission == PermissionStatus.APPROVAL_REQUIRED:
            status = "WARNING_APPROVAL_REQUIRED"
        else:
            status = "WARNING_TERMS_UNVERIFIED"
        return LaunchGateResult(False, status, tuple(reasons))
    return LaunchGateResult(True, "TERMS_OK", ())
