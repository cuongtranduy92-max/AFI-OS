from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from afi_os.db import get_db
from afi_os.enums import CaptureStatus
from afi_os.models import AdObservation, Advertiser, Campaign, Program, Project, RawCapture
from afi_os.schemas import DashboardSummary
from afi_os.services.programs import program_gate_status

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db)) -> DashboardSummary:
    programs = list(
        db.scalars(
            select(Program).options(
                selectinload(Program.terms_evidence),
                selectinload(Program.terms_research_runs),
            )
        ).all()
    )
    ready_statuses = {"TERMS_OK"}
    gate_statuses = [
        program_gate_status(program, list(program.terms_evidence))
        for program in programs
    ]
    allowed = sum(status in ready_statuses for status in gate_statuses)
    blocked = len(gate_statuses) - allowed
    needs_review = int(
        db.scalar(
            select(func.count())
            .select_from(RawCapture)
            .where(
                RawCapture.status.in_({CaptureStatus.RAW, CaptureStatus.NEEDS_REVIEW})
            )
            .where(
                ~select(AdObservation.id)
                .where(AdObservation.raw_capture_id == RawCapture.id)
                .exists()
            )
        )
        or 0
    )
    last_capture = db.scalar(select(func.max(RawCapture.captured_at)))
    return DashboardSummary(
        projects=_count(db, Project),
        advertisers=_count(db, Advertiser),
        observations=_count(db, AdObservation),
        programs=len(programs),
        programs_explicitly_allowed=allowed,
        programs_blocked_pending_evidence=blocked,
        programs_terms_ok=allowed,
        programs_with_terms_warnings=blocked,
        campaigns=_count(db, Campaign),
        active_campaigns=int(
            db.scalar(
                select(func.count()).select_from(Campaign).where(
                    func.upper(Campaign.status).in_(["ENABLED", "ACTIVE"])
                )
            )
            or 0
        ),
        captures_needing_review=needs_review,
        last_capture_at=last_capture,
    )
