from __future__ import annotations

from datetime import UTC, datetime

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AuditAction, ResearchStatus
from afi_os.models import AuditLog, Merchant, Program, TermsResearchRun
from afi_os.services.operations import operations_inbox


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _program_with_run(
    domain: str,
    *,
    status: ResearchStatus,
    stored_sources: list[str],
    attempt_sources: list[str],
    priority_sources: list[str] | None = None,
) -> tuple[int, int]:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        merchant = Merchant(name=domain, website_domain=domain)
        db.add(merchant)
        db.flush()
        program = Program(merchant_id=merchant.id, name=f"{domain} Affiliate")
        db.add(program)
        db.flush()
        run = TermsResearchRun(
            program_id=program.id,
            domain=domain,
            fixture_version="attempt-source-warning-test",
            status=status,
            checked_at=now,
            discovery_confidence=0.0,
            source_urls=stored_sources,
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash=f"{domain}-{status.value}".ljust(64, "x")[:64],
            summary="Attempt source warning test.",
        )
        db.add(run)
        db.flush()
        db.add(
            AuditLog(
                entity_type="terms_research_run",
                entity_id=str(run.id),
                action=AuditAction.IMPORT,
                actor="official-web-v1",
                payload_json={
                    "domain": domain,
                    "source_urls": attempt_sources,
                    "priority_source_urls": priority_sources or [],
                    "permissions_changed": False,
                },
            )
        )
        db.commit()
        return program.id, run.id


def test_no_permission_warning_counts_latest_attempt_sources() -> None:
    domain = "attempt-warning.example.org"
    old_url = f"https://{domain}/affiliate-program"
    extra_url = f"https://{domain}/partner-policy"
    program_id, _run_id = _program_with_run(
        domain,
        status=ResearchStatus.PROPOSAL_READY,
        stored_sources=[old_url],
        attempt_sources=[old_url, extra_url],
    )

    with SessionLocal() as db:
        inbox = operations_inbox(db)

    warning = next(
        item
        for item in inbox["items"]
        if item["key"] == f"TERMS_NO_PERMISSION_EVIDENCE:{program_id}"
    )
    assert "đã đọc 2 URL nguồn" in warning["detail"]
    assert warning["source_url"] is None
    assert warning["requires_user"] is False


def test_manual_warning_links_current_attempt_before_stale_run_source() -> None:
    domain = "manual-attempt-warning.example.org"
    stale_url = f"https://{domain}/affiliate-old"
    current_url = f"https://{domain}/affiliate-current"
    _program_id, run_id = _program_with_run(
        domain,
        status=ResearchStatus.MANUAL_INPUT_REQUIRED,
        stored_sources=[stale_url],
        attempt_sources=[current_url],
    )

    with SessionLocal() as db:
        inbox = operations_inbox(db)

    warning = next(
        item for item in inbox["items"] if item["key"] == f"TERMS_MANUAL:{domain}"
    )
    assert warning["entity_id"] == str(run_id)
    assert warning["source_url"] == current_url
    assert warning["source_url"] != stale_url
