from datetime import UTC, datetime, timedelta

from afi_os.enums import EvidenceReviewStatus, PermissionStatus, SourceAuthority
from afi_os.services.compliance import EvidenceSnapshot, LaunchGateInput, evaluate_launch_gate


def accepted_evidence(
    scope: str,
    decision: PermissionStatus,
    **overrides,
) -> EvidenceSnapshot:
    values = {
        "scope": scope,
        "decision": decision,
        "source_url": "https://example.com/affiliate-terms",
        "source_authority": SourceAuthority.OFFICIAL,
        "review_status": EvidenceReviewStatus.ACCEPTED,
        "checked_at": datetime.now(UTC),
        "confidence": 0.95,
    }
    values.update(overrides)
    return EvidenceSnapshot(**values)


def test_ambiguous_is_blocked() -> None:
    result = evaluate_launch_gate(
        LaunchGateInput(
            merchant_domain="example.com",
            paid_search_permission=PermissionStatus.AMBIGUOUS,
            brand_keyword_permission=PermissionStatus.AMBIGUOUS,
            non_brand_permission=PermissionStatus.AMBIGUOUS,
            direct_link_permission=PermissionStatus.NOT_CHECKED,
            wants_brand_keywords=False,
            wants_direct_link=False,
        )
    )
    assert result.allowed is False
    assert result.status == "WARNING_TERMS_UNVERIFIED"


def test_brand_requires_separate_accepted_scoped_evidence() -> None:
    result = evaluate_launch_gate(
        LaunchGateInput(
            merchant_domain="example.com",
            paid_search_permission=PermissionStatus.BRAND_ALLOWED,
            brand_keyword_permission=PermissionStatus.BRAND_ALLOWED,
            non_brand_permission=PermissionStatus.BRAND_ALLOWED,
            direct_link_permission=PermissionStatus.PROHIBITED,
            wants_brand_keywords=True,
            wants_direct_link=False,
            evidence=(
                accepted_evidence("PAID_SEARCH", PermissionStatus.BRAND_ALLOWED),
                accepted_evidence("BRAND_KEYWORD", PermissionStatus.BRAND_ALLOWED),
            ),
        )
    )
    assert result.allowed is True
    assert result.status == "TERMS_OK"


def test_non_brand_only_paid_search_cannot_authorize_brand_bidding() -> None:
    result = evaluate_launch_gate(
        LaunchGateInput(
            merchant_domain="example.com",
            paid_search_permission=PermissionStatus.NON_BRAND_ONLY,
            brand_keyword_permission=PermissionStatus.BRAND_ALLOWED,
            non_brand_permission=PermissionStatus.NON_BRAND_ONLY,
            direct_link_permission=PermissionStatus.PROHIBITED,
            wants_brand_keywords=True,
            wants_direct_link=False,
            evidence=(
                accepted_evidence("PAID_SEARCH", PermissionStatus.NON_BRAND_ONLY),
                accepted_evidence("BRAND_KEYWORD", PermissionStatus.BRAND_ALLOWED),
            ),
        )
    )

    assert result.allowed is False
    assert result.status == "WARNING_TERMS_UNVERIFIED"


def test_non_brand_blocks_unsourced_proposed_or_wrong_scope_evidence() -> None:
    base = {
        "merchant_domain": "example.com",
        "paid_search_permission": PermissionStatus.NON_BRAND_ONLY,
        "brand_keyword_permission": PermissionStatus.PROHIBITED,
        "non_brand_permission": PermissionStatus.NON_BRAND_ONLY,
        "direct_link_permission": PermissionStatus.PROHIBITED,
        "wants_brand_keywords": False,
        "wants_direct_link": False,
    }
    unsafe_items = (
        accepted_evidence("PAID_SEARCH", PermissionStatus.NON_BRAND_ONLY),
        accepted_evidence(
            "NON_BRAND",
            PermissionStatus.NON_BRAND_ONLY,
            review_status=EvidenceReviewStatus.PROPOSED,
        ),
        accepted_evidence(
            "DIRECT_LINK",
            PermissionStatus.NON_BRAND_ONLY,
            source_authority=SourceAuthority.THIRD_PARTY,
        ),
    )

    result = evaluate_launch_gate(LaunchGateInput(**base, evidence=unsafe_items))

    assert result.allowed is False
    assert result.status == "WARNING_TERMS_UNVERIFIED"
    assert any("Non-brand" in reason for reason in result.reasons)


def test_future_dated_evidence_cannot_open_gate() -> None:
    result = evaluate_launch_gate(
        LaunchGateInput(
            merchant_domain="example.com",
            paid_search_permission=PermissionStatus.NON_BRAND_ONLY,
            brand_keyword_permission=PermissionStatus.PROHIBITED,
            non_brand_permission=PermissionStatus.NON_BRAND_ONLY,
            direct_link_permission=PermissionStatus.PROHIBITED,
            wants_brand_keywords=False,
            wants_direct_link=False,
            evidence=(
                accepted_evidence(
                    "PAID_SEARCH",
                    PermissionStatus.NON_BRAND_ONLY,
                    checked_at=datetime.now(UTC) + timedelta(days=1),
                ),
                accepted_evidence("NON_BRAND", PermissionStatus.NON_BRAND_ONLY),
            ),
        )
    )

    assert result.allowed is False
    assert result.status == "WARNING_TERMS_UNVERIFIED"


def test_conflicting_accepted_evidence_is_blocked() -> None:
    result = evaluate_launch_gate(
        LaunchGateInput(
            merchant_domain="example.com",
            paid_search_permission=PermissionStatus.CONFLICT,
            brand_keyword_permission=PermissionStatus.NOT_CHECKED,
            non_brand_permission=PermissionStatus.NOT_CHECKED,
            direct_link_permission=PermissionStatus.NOT_CHECKED,
            wants_brand_keywords=False,
            wants_direct_link=False,
            evidence=(
                accepted_evidence("PAID_SEARCH", PermissionStatus.NON_BRAND_ONLY),
                accepted_evidence("PAID_SEARCH", PermissionStatus.PROHIBITED),
            ),
        )
    )

    assert result.allowed is False
    assert result.status == "WARNING_TERMS_CONFLICT"
