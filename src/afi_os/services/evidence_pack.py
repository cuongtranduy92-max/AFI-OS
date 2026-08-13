from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from afi_os.models import AuditLog, Program
from afi_os.services.programs import (
    commission_resolution_status,
    latest_research_run,
    program_gate_status,
    program_signup_source_authority,
)
from afi_os.services.terms_research import source_authorities_from_audit_payload

PACK_FORMAT_VERSION = 4
PERMISSION_FIELDS = (
    "paid_search_permission",
    "brand_keyword_permission",
    "non_brand_permission",
    "direct_link_permission",
    "trademark_in_ad_copy_permission",
)
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    return value


def _csv_safe(value: Any) -> str:
    normalized = _value(value)
    if normalized is None:
        return ""
    if isinstance(normalized, (dict, list)):
        text = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            default=_value,
        )
    else:
        text = str(normalized)
    if text.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _csv_bytes(fieldnames: list[str], rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_safe(row.get(field)) for field in fieldnames})
    return output.getvalue().encode("utf-8-sig")


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_value)
        + "\n"
    ).encode("utf-8")


def _safe_domain(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9.-]+", "-", value.lower()).strip("-.")
    return normalized[:120] or "program"


def _attempt_rows(db: Session, run_ids: list[int]) -> list[dict[str, Any]]:
    if not run_ids:
        return []
    audits = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "terms_research_run",
            AuditLog.entity_id.in_([str(run_id) for run_id in run_ids]),
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    ).all()
    rows: list[dict[str, Any]] = []
    for audit in audits:
        payload = audit.payload_json if isinstance(audit.payload_json, dict) else {}
        source_snapshots = payload.get("source_snapshots", [])
        if not isinstance(source_snapshots, list):
            source_snapshots = []
        truncated_source_urls = sorted(
            {
                item.get("url")
                for item in source_snapshots
                if isinstance(item, dict)
                and item.get("truncated") is True
                and isinstance(item.get("url"), str)
            }
        )
        rows.append(
            {
                "audit_id": audit.id,
                "run_id": audit.entity_id,
                "attempted_at": audit.created_at,
                "actor": audit.actor,
                "action": audit.action,
                "duplicate_run": payload.get("duplicate_run") is True,
                "source_urls": payload.get("source_urls", []),
                "priority_source_urls": payload.get("priority_source_urls", []),
                "source_authorities": source_authorities_from_audit_payload(payload),
                "collection_errors": payload.get("collection_errors", []),
                "source_page_count": len(source_snapshots),
                "truncated_source_urls": truncated_source_urls,
                "source_change_status": payload.get("source_change_status"),
                "source_changes": payload.get("source_changes", []),
                "imported_terms_evidence": payload.get("imported_terms_evidence", 0),
                "duplicate_terms_evidence": payload.get("duplicate_terms_evidence", 0),
                "refreshed_terms_evidence": payload.get("refreshed_terms_evidence", 0),
                "imported_commission_facts": payload.get(
                    "imported_commission_facts", 0
                ),
                "duplicate_commission_facts": payload.get(
                    "duplicate_commission_facts", 0
                ),
                "refreshed_commission_facts": payload.get(
                    "refreshed_commission_facts", 0
                ),
                "permissions_changed": payload.get("permissions_changed") is True,
            }
        )
    return rows


def _review_audit_rows(
    db: Session,
    evidence_ids: list[int],
    fact_ids: list[int],
) -> list[dict[str, Any]]:
    conditions = []
    if evidence_ids:
        conditions.append(
            and_(
                AuditLog.entity_type == "terms_evidence",
                AuditLog.entity_id.in_([str(item_id) for item_id in evidence_ids]),
            )
        )
    if fact_ids:
        conditions.append(
            and_(
                AuditLog.entity_type == "commission_fact",
                AuditLog.entity_id.in_([str(item_id) for item_id in fact_ids]),
            )
        )
    if not conditions:
        return []
    audits = db.scalars(
        select(AuditLog)
        .where(or_(*conditions))
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    ).all()
    allowed_payload_fields = (
        "program_id",
        "scope",
        "decision",
        "confidence",
        "review_status",
        "commission_type",
        "commission_rate",
        "metadata_refreshed",
        "permissions_changed",
    )
    return [
        {
            "audit_id": audit.id,
            "entity_type": audit.entity_type,
            "entity_id": audit.entity_id,
            "action": audit.action,
            "actor": audit.actor,
            "created_at": audit.created_at,
            "decision_metadata": {
                key: audit.payload_json.get(key)
                for key in allowed_payload_fields
                if isinstance(audit.payload_json, dict) and key in audit.payload_json
            },
        }
        for audit in audits
    ]


def build_program_evidence_pack(
    db: Session,
    program: Program,
    *,
    exported_at: datetime | None = None,
) -> tuple[str, bytes]:
    exported_at = exported_at or datetime.now(UTC)
    if exported_at.tzinfo is None:
        exported_at = exported_at.replace(tzinfo=UTC)
    exported_at = exported_at.astimezone(UTC)

    evidence = sorted(
        program.terms_evidence,
        key=lambda item: (_value(item.checked_at), item.id),
    )
    facts = sorted(
        program.commission_facts,
        key=lambda item: (_value(item.checked_at), item.id),
    )
    runs = sorted(
        program.terms_research_runs,
        key=lambda item: (_value(item.checked_at), item.id),
    )
    attempts = _attempt_rows(db, [item.id for item in runs])
    review_audits = _review_audit_rows(
        db,
        [item.id for item in evidence],
        [item.id for item in facts],
    )
    latest_run = latest_research_run(runs)
    latest_attempt = attempts[-1] if attempts else None
    signup_source_authority = program_signup_source_authority(
        program.signup_url,
        program.merchant.website_domain,
    )
    permissions = {
        field: _value(getattr(program, field)) for field in PERMISSION_FIELDS
    }
    source_urls = sorted(
        url
        for url in {
            program.signup_url,
            *(item.source_url for item in evidence),
            *(item.source_url for item in facts),
            *(url for run in runs for url in run.source_urls),
        }
        if isinstance(url, str) and url
    )

    summary = {
        "pack_format_version": PACK_FORMAT_VERSION,
        "exported_at": exported_at,
        "program": {
            "id": program.id,
            "merchant_name": program.merchant.name,
            "merchant_domain": program.merchant.website_domain,
            "program_name": program.name,
            "network_name": program.network.name if program.network else None,
            "signup_url": program.signup_url,
            "signup_source_authority": signup_source_authority,
            "status": program.status,
            "notes": program.notes,
        },
        "canonical_permissions": permissions,
        "program_gate_status": program_gate_status(program, evidence),
        "commission_state": commission_resolution_status(facts),
        "last_terms_checked_at": program.last_terms_checked_at,
        "latest_research": (
            {
                "run_id": latest_run.id,
                "status": latest_run.status,
                "checked_at": latest_run.checked_at,
                "discovery_confidence": latest_run.discovery_confidence,
                "summary": latest_run.summary,
            }
            if latest_run is not None
            else None
        ),
        "counts": {
            "terms_evidence": len(evidence),
            "commission_facts": len(facts),
            "research_runs": len(runs),
            "research_attempts": len(attempts),
            "review_audit_events": len(review_audits),
            "source_urls": len(source_urls),
        },
        "source_urls": source_urls,
        "collection": {
            "latest_source_page_count": (
                latest_attempt["source_page_count"] if latest_attempt else 0
            ),
            "latest_truncated_source_urls": (
                latest_attempt["truncated_source_urls"] if latest_attempt else []
            ),
            "latest_source_authorities": (
                latest_attempt["source_authorities"] if latest_attempt else {}
            ),
            "large_pages_are_bounded_to_bytes": 1_000_000,
        },
        "safety": {
            "export_is_read_only": True,
            "permissions_changed_by_export": False,
            "projects_or_campaigns_excluded_by_export": False,
            "commission_is_separate_from_ppc_permissions": True,
        },
    }

    evidence_rows = [
        {
            "id": item.id,
            "scope": item.scope,
            "decision": item.decision,
            "review_status": item.review_status,
            "source_url": item.source_url,
            "source_type": item.source_type,
            "source_authority": item.source_authority,
            "excerpt": item.excerpt,
            "checked_at": item.checked_at,
            "expires_at": item.expires_at,
            "confidence": item.confidence,
            "reviewer": item.reviewer,
            "collected_by": item.collected_by,
            "reviewed_at": item.reviewed_at,
            "reviewed_by": item.reviewed_by,
            "notes": item.notes,
            "evidence_hash": item.evidence_hash,
        }
        for item in evidence
    ]
    commission_rows = [
        {
            "id": item.id,
            "scope": item.scope,
            "commission_type": item.commission_type,
            "commission_rate": item.commission_rate,
            "rate_is_maximum": item.rate_is_maximum,
            "applies_to": item.applies_to,
            "review_status": item.review_status,
            "source_url": item.source_url,
            "source_authority": item.source_authority,
            "excerpt": item.excerpt,
            "checked_at": item.checked_at,
            "confidence": item.confidence,
            "collected_by": item.collected_by,
            "notes": item.notes,
            "evidence_hash": item.evidence_hash,
        }
        for item in facts
    ]
    research_rows = [
        {
            "run_id": item.id,
            "domain": item.domain,
            "status": item.status,
            "checked_at": item.checked_at,
            "discovery_confidence": item.discovery_confidence,
            "fixture_version": item.fixture_version,
            "source_urls": item.source_urls,
            "permission_proposals": item.permission_proposals,
            "imported_fact_ids": item.imported_fact_ids,
            "summary": item.summary,
            "run_hash": item.run_hash,
        }
        for item in runs
    ]

    files: dict[str, bytes] = {
        "program-summary.json": _json_bytes(summary),
        "terms-evidence.csv": _csv_bytes(
            [
                "id",
                "scope",
                "decision",
                "review_status",
                "source_url",
                "source_type",
                "source_authority",
                "excerpt",
                "checked_at",
                "expires_at",
                "confidence",
                "reviewer",
                "collected_by",
                "reviewed_at",
                "reviewed_by",
                "notes",
                "evidence_hash",
            ],
            evidence_rows,
        ),
        "commission-facts.csv": _csv_bytes(
            [
                "id",
                "scope",
                "commission_type",
                "commission_rate",
                "rate_is_maximum",
                "applies_to",
                "review_status",
                "source_url",
                "source_authority",
                "excerpt",
                "checked_at",
                "confidence",
                "collected_by",
                "notes",
                "evidence_hash",
            ],
            commission_rows,
        ),
        "research-runs.csv": _csv_bytes(
            [
                "run_id",
                "domain",
                "status",
                "checked_at",
                "discovery_confidence",
                "fixture_version",
                "source_urls",
                "permission_proposals",
                "imported_fact_ids",
                "summary",
                "run_hash",
            ],
            research_rows,
        ),
        "research-attempts.csv": _csv_bytes(
            [
                "audit_id",
                "run_id",
                "attempted_at",
                "actor",
                "action",
                "duplicate_run",
                "source_urls",
                "priority_source_urls",
                "source_authorities",
                "collection_errors",
                "source_page_count",
                "truncated_source_urls",
                "source_change_status",
                "source_changes",
                "imported_terms_evidence",
                "duplicate_terms_evidence",
                "refreshed_terms_evidence",
                "imported_commission_facts",
                "duplicate_commission_facts",
                "refreshed_commission_facts",
                "permissions_changed",
            ],
            attempts,
        ),
        "review-audit.csv": _csv_bytes(
            [
                "audit_id",
                "entity_type",
                "entity_id",
                "action",
                "actor",
                "created_at",
                "decision_metadata",
            ],
            review_audits,
        ),
    }

    readme = f"""AFI-OS TERMS EVIDENCE PACK
==========================

Merchant: {program.merchant.name}
Domain: {program.merchant.website_domain}
Program: {program.name}
Exported at (UTC): {exported_at.isoformat()}

SIGNUP SOURCE
-------------
URL: {program.signup_url or 'Not recorded'}
Authority: {_value(signup_source_authority) or 'UNKNOWN'}

CANONICAL PPC STATE
-------------------
Paid search: {permissions['paid_search_permission']}
Brand keyword: {permissions['brand_keyword_permission']}
Non-brand: {permissions['non_brand_permission']}
Direct link: {permissions['direct_link_permission']}
Trademark in ad copy: {permissions['trademark_in_ad_copy_permission']}
Gate: {summary['program_gate_status']}

COMMISSION
----------
State: {summary['commission_state']}
Facts: {len(facts)}
Commission facts are stored separately and never prove PPC permission.

CONTENTS
--------
- program-summary.json: canonical state, source list, counts and safety flags.
- terms-evidence.csv: URL, verbatim excerpt, checked_at, confidence, scope and review state.
- commission-facts.csv: source-backed commission claims kept separate from PPC.
- research-runs.csv: automated domain research results and sources checked.
- research-attempts.csv: heartbeat attempts, URL source authority, source changes,
  truncated-page markers and collection errors.
- review-audit.csv: evidence/commission decision events and safety metadata.
- manifest.json: SHA-256 for every file in this pack.

SAFETY
------
This export is read-only. It does not accept a proposal, change any permission,
exclude or stop a project/campaign, or write to Google Ads. CSV cells beginning
with spreadsheet formula characters are prefixed with an apostrophe.
"""
    files["README.txt"] = readme.encode("utf-8")

    manifest = {
        "pack_format_version": PACK_FORMAT_VERSION,
        "exported_at": exported_at,
        "program_id": program.id,
        "merchant_domain": program.merchant.website_domain,
        "files": [
            {
                "path": name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(files.items())
        ],
    }
    files["manifest.json"] = _json_bytes(manifest)

    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as bundle:
        for name, content in sorted(files.items()):
            bundle.writestr(name, content)

    filename = (
        f"AFI-OS-evidence-{_safe_domain(program.merchant.website_domain)}-"
        f"{exported_at:%Y%m%d-%H%M%S}.zip"
    )
    return filename, archive.getvalue()
