from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from afi_os.enums import (
    AuditAction,
    ProgramStatus,
    ProjectStage,
    RegistrationStatus,
    WatchStatus,
)
from afi_os.models import AuditLog, Program, Project


PROGRAM_WORKFLOW = {
    ProgramStatus.ACTIVE: (
        ProjectStage.LIVE,
        RegistrationStatus.APPROVED,
        "Theo dõi campaign và doanh thu",
    ),
    ProgramStatus.PAUSED: (
        ProjectStage.PAUSED,
        RegistrationStatus.BLOCKED_REGISTRATION,
        "Kiểm tra lại khả năng đăng ký hoặc giữ PAUSED",
    ),
    ProgramStatus.REJECTED: (
        ProjectStage.CLOSED,
        RegistrationStatus.REJECTED,
        "Giữ hồ sơ và lý do bị từ chối",
    ),
    ProgramStatus.CLOSED: (
        ProjectStage.CLOSED,
        RegistrationStatus.CLOSED,
        "Giữ hồ sơ để đối chiếu lịch sử",
    ),
    ProgramStatus.APPLYING: (
        ProjectStage.PREP,
        RegistrationStatus.APPLYING,
        "Hoàn tất hồ sơ đăng ký",
    ),
    ProgramStatus.PENDING_APPROVAL: (
        ProjectStage.PREP,
        RegistrationStatus.PENDING_APPROVAL,
        "Theo dõi phản hồi đăng ký",
    ),
    ProgramStatus.DISCOVERED: (
        ProjectStage.RESEARCH,
        RegistrationStatus.NOT_STARTED,
        "Hoàn tất research và hồ sơ đăng ký",
    ),
}


def ensure_project_for_program(
    db: Session,
    program: Program,
    *,
    actor: str = "program-project-sync-v1",
) -> tuple[Project, str]:
    """Retain every Program in Portfolio without overwriting operator workflow."""

    domain = program.merchant.website_domain
    project = db.scalar(select(Project).where(Project.domain == domain))
    if project is not None:
        before = {
            "program_id": project.program_id,
            "affiliate_program_found": project.affiliate_program_found,
        }
        if project.program_id is None:
            project.program_id = program.id
        project.affiliate_program_found = True
        after = {
            "program_id": project.program_id,
            "affiliate_program_found": project.affiliate_program_found,
        }
        if before != after:
            db.add(
                AuditLog(
                    entity_type="project_program_sync",
                    entity_id=str(project.id),
                    action=AuditAction.UPDATE,
                    actor=actor,
                    payload_json={
                        "domain": domain,
                        "before": before,
                        "after": after,
                        "workflow_preserved": True,
                        "warning_only": True,
                        "google_ads_write": False,
                    },
                )
            )
            db.flush()
            return project, "LINKED"
        return project, "PRESERVED"

    stage, registration_status, next_action = PROGRAM_WORKFLOW[program.status]
    observed_at = program.created_at or datetime.now(UTC)
    project = Project(
        domain=domain,
        brand_name=program.merchant.name,
        affiliate_program_found=True,
        program_id=program.id,
        watch_status=WatchStatus.WATCH,
        stage=stage,
        registration_status=registration_status,
        next_action=next_action,
        first_seen_at=observed_at,
        last_seen_at=program.updated_at or observed_at,
    )
    db.add(project)
    db.flush()
    db.add(
        AuditLog(
            entity_type="project_program_sync",
            entity_id=str(project.id),
            action=AuditAction.CREATE,
            actor=actor,
            payload_json={
                "domain": domain,
                "program_id": program.id,
                "stage": stage.value,
                "registration_status": registration_status.value,
                "warning_only": True,
                "google_ads_write": False,
            },
        )
    )
    return project, "CREATED"


def sync_program_projects(
    db: Session,
    *,
    actor: str = "program-project-sync-v1",
) -> dict[str, int]:
    programs = list(
        db.scalars(
            select(Program)
            .options(selectinload(Program.merchant))
            .order_by(Program.id.asc())
        ).all()
    )
    counts = {"scanned": len(programs), "created": 0, "linked": 0, "preserved": 0}
    for program in programs:
        _project, result = ensure_project_for_program(db, program, actor=actor)
        counts[result.lower()] += 1
    db.flush()
    return counts
