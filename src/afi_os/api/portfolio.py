from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.enums import (
    AuditAction,
    DataQuality,
    ProjectStage,
    RegistrationStatus,
    WatchStatus,
)
from afi_os.models import AuditLog, MetricSnapshot, Project
from afi_os.schemas import (
    MetricEnvelope,
    ProjectAutoCheckResponse,
    ProjectCheckSourceResult,
    ProjectIntakeRequest,
    ProjectIntakeResponse,
    ProjectPortfolioItem,
    ProjectStepOneDecisionRequest,
    ProjectStepOneDecisionResponse,
    ProjectStepOneResponse,
    ProjectTrafficSnapshotRequest,
    ProjectTrafficSnapshotResponse,
    ProjectWorkflowUpdate,
)
from afi_os.services.google_ads_keyword_check import collect_project_keyword_metrics
from afi_os.services.llm_terms import LLMExtractionError, extract_terms_from_pages
from afi_os.services.portfolio import (
    build_portfolio_item,
    load_portfolio_project,
    load_portfolio_projects,
)
from afi_os.services.project_check import build_project_step_one
from afi_os.services.project_sync import ensure_project_for_program
from afi_os.services.terms_research import collect_domain_proposal
from afi_os.services.traffic_provider import collect_project_traffic

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _brand_name_from_domain(domain: str) -> str:
    label = domain.split(".", 1)[0].replace("-", " ").strip()
    return label.title() or domain


def _sort_value(item: ProjectPortfolioItem, key: str) -> Any:
    if key == "confidence":
        return item.evidence_confidence
    if key == "advertisers":
        return item.metrics["independent_advertisers"].value
    if key == "ctr":
        return item.metrics["ctr"].value
    if key == "brand":
        return item.brand_name.lower()
    return item.updated_at


@router.get("/projects", response_model=list[ProjectPortfolioItem])
def list_portfolio_projects(
    query: str | None = Query(default=None, max_length=255),
    stage: ProjectStage | None = None,
    registration_status: RegistrationStatus | None = None,
    risk: str | None = Query(default=None, max_length=80),
    sort: str = Query(default="updated", pattern="^(updated|confidence|advertisers|ctr|brand)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[ProjectPortfolioItem]:
    items = [build_portfolio_item(project) for project in load_portfolio_projects(db)]
    if query:
        needle = query.strip().lower()
        items = [
            item
            for item in items
            if needle in item.brand_name.lower() or needle in item.domain.lower()
        ]
    if stage is not None:
        items = [item for item in items if item.stage == stage]
    if registration_status is not None:
        items = [item for item in items if item.registration_status == registration_status]
    if risk:
        items = [item for item in items if risk in item.risk_badges]
    if sort in {"advertisers", "ctr"}:
        known = [item for item in items if _sort_value(item, sort) is not None]
        missing = [item for item in items if _sort_value(item, sort) is None]
        known.sort(
            key=lambda item: _sort_value(item, sort),
            reverse=direction == "desc",
        )
        items = known + missing
    else:
        items.sort(key=lambda item: _sort_value(item, sort), reverse=direction == "desc")
    return items[:limit]


@router.post("/projects/intake", response_model=ProjectIntakeResponse)
def intake_portfolio_project(
    payload: ProjectIntakeRequest,
    db: Session = Depends(get_db),
) -> ProjectIntakeResponse:
    """Retain a domain immediately; enrichment is incremental and warning-only."""

    project = db.scalar(select(Project).where(Project.domain == payload.domain))
    created = project is None
    if project is None:
        now = datetime.now(UTC)
        project = Project(
            domain=payload.domain,
            brand_name=_brand_name_from_domain(payload.domain),
            affiliate_program_found=False,
            watch_status=WatchStatus.WATCH,
            stage=ProjectStage.INTAKE,
            registration_status=RegistrationStatus.NOT_STARTED,
            next_action="Đang rà chương trình affiliate, điều khoản và commission",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(project)
        db.flush()
        db.add(
            AuditLog(
                entity_type="project_intake",
                entity_id=str(project.id),
                action=AuditAction.CREATE,
                actor=payload.actor,
                payload_json={
                    "domain": payload.domain,
                    "warning_only": True,
                    "permissions_changed": False,
                    "campaign_state_changed": False,
                    "google_ads_write": False,
                },
            )
        )
    db.commit()
    loaded = load_portfolio_project(db, project.id)
    assert loaded is not None
    return ProjectIntakeResponse(
        project=build_portfolio_item(loaded),
        created=created,
    )


def run_auto_check_portfolio_project(
    payload: ProjectIntakeRequest,
    db: Session,
    *,
    traffic_override: dict | None = None,
) -> ProjectAutoCheckResponse:
    """Run one source-aware check from a domain without asking for metric inputs."""

    project = db.scalar(select(Project).where(Project.domain == payload.domain))
    if project is None:
        now = datetime.now(UTC)
        project = Project(
            domain=payload.domain,
            brand_name=_brand_name_from_domain(payload.domain),
            affiliate_program_found=False,
            watch_status=WatchStatus.WATCH,
            stage=ProjectStage.INTAKE,
            registration_status=RegistrationStatus.NOT_STARTED,
            next_action="Đang tự động thu thập nguồn cho Bước 1",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(project)
        db.flush()
        db.add(
            AuditLog(
                entity_type="project_intake",
                entity_id=str(project.id),
                action=AuditAction.CREATE,
                actor=payload.actor,
                payload_json={
                    "domain": payload.domain,
                    "entry_type": "AUTO_CHECK",
                    "permissions_changed": False,
                    "campaign_state_changed": False,
                    "google_ads_write": False,
                },
            )
        )
        db.commit()

    source_results: list[ProjectCheckSourceResult] = []
    try:
        terms = collect_domain_proposal(db, payload.domain)
        program = terms.get("program")
        if program is not None:
            ensure_project_for_program(db, program)
            project = db.scalar(select(Project).where(Project.domain == payload.domain)) or project
        source_results.append(
            ProjectCheckSourceResult(
                source="Affiliate & Terms",
                status=terms["run"].status.value,
                detail=(
                    f"Đã đọc {len(terms.get('source_urls', []))} nguồn; "
                    "PPC chỉ là proposal/cảnh báo cho tới khi đủ bằng chứng."
                ),
                fields=["affiliate_signup_url", "accepted_commission_rate", "ppc_permissions"],
                source_urls=list(terms.get("source_urls", [])),
            )
        )
        project = db.scalar(select(Project).where(Project.domain == payload.domain)) or project
        loaded_for_llm = load_portfolio_project(db, project.id) or project
        try:
            llm = extract_terms_from_pages(
                db,
                loaded_for_llm,
                list(terms.get("pages") or []),
            )
            proposal_count = (
                len(llm["commission_facts"])
                + len(llm["terms_evidence"])
                + len(llm["commercial_proposals"])
            )
            source_results.append(
                ProjectCheckSourceResult(
                    source="Claude · Terms/Pricing/Commission",
                    status=str(llm["status"]),
                    detail=(
                        f"{proposal_count} đề xuất có trích dẫn; "
                        + (
                            "dùng cache, không tốn lượt gọi mới. "
                            if llm["cached"]
                            else "đã trích xuất mới. "
                        )
                        + "Chỉ dùng sau khi anh xác nhận."
                    ),
                    fields=[
                        "accepted_commission_rate",
                        "average_package_price",
                        "payout_methods",
                        "ppc_permissions",
                    ],
                    source_urls=list(llm["source_urls"]),
                )
            )
        except LLMExtractionError as exc:
            source_results.append(
                ProjectCheckSourceResult(
                    source="Claude · Terms/Pricing/Commission",
                    status=exc.status,
                    detail=exc.detail,
                    requires_user=exc.status in {"CONNECTION_REQUIRED", "AUTH_FAILED"},
                    fields=[
                        "accepted_commission_rate",
                        "average_package_price",
                        "payout_methods",
                        "ppc_permissions",
                    ],
                    source_urls=list(terms.get("source_urls", [])),
                    setup_command=(
                        "SETUP-LLM.command" if exc.status == "CONNECTION_REQUIRED" else None
                    ),
                )
            )
    except Exception as exc:
        source_results.append(
            ProjectCheckSourceResult(
                source="Affiliate & Terms",
                status="RETRY_REQUIRED",
                detail=f"Chưa đọc được nguồn công khai: {type(exc).__name__}",
                requires_user=False,
                fields=["affiliate_signup_url", "accepted_commission_rate", "ppc_permissions"],
            )
        )

    project = db.scalar(select(Project).where(Project.domain == payload.domain)) or project
    traffic = traffic_override or collect_project_traffic(db, project)
    source_results.append(
        ProjectCheckSourceResult(
            source=f"Traffic website · {traffic.get('provider') or 'chưa kết nối'}",
            status=str(traffic["status"]),
            detail=str(traffic["detail"]),
            requires_user=bool(traffic.get("requires_user")),
            fields=list(traffic.get("fields", [])),
            source_urls=list(traffic.get("source_urls", [])),
            setup_command=traffic.get("setup_command"),
        )
    )

    keyword = collect_project_keyword_metrics(db, project)
    source_results.append(
        ProjectCheckSourceResult(
            source="Từ khóa & CPC",
            status=str(keyword["status"]),
            detail=str(keyword["detail"]),
            requires_user=bool(keyword.get("requires_user")),
            fields=list(keyword.get("fields", [])),
            source_urls=list(keyword.get("source_urls", [])),
        )
    )

    loaded = load_portfolio_project(db, project.id)
    assert loaded is not None
    step_one = build_project_step_one(loaded)
    covered_groups = {"Affiliate & Terms", "Traffic thị trường", "Từ khóa & CPC"}
    for need in step_one.collection_needs:
        if need.group in covered_groups:
            continue
        source_results.append(
            ProjectCheckSourceResult(
                source=need.group,
                status=need.status,
                detail=need.source_required,
                requires_user=need.status == "NEEDS_CONNECTION",
                fields=need.fields,
            )
        )
    db.add(
        AuditLog(
            entity_type="project_auto_check",
            entity_id=str(project.id),
            action=AuditAction.IMPORT,
            actor=payload.actor,
            payload_json={
                "domain": payload.domain,
                "source_statuses": [item.model_dump(mode="json") for item in source_results],
                "decision_ready": step_one.decision_ready,
                "blocking_fields": step_one.blocking_fields,
                "permissions_changed": False,
                "campaign_state_changed": False,
                "google_ads_write": False,
            },
        )
    )
    db.commit()
    loaded = load_portfolio_project(db, project.id)
    assert loaded is not None
    return ProjectAutoCheckResponse(
        project=build_portfolio_item(loaded),
        step_one=build_project_step_one(loaded),
        sources=source_results,
        decision_ready=step_one.decision_ready,
        blocking_fields=step_one.blocking_fields,
    )


@router.post("/projects/auto-check", response_model=ProjectAutoCheckResponse)
def auto_check_portfolio_project(
    payload: ProjectIntakeRequest,
    db: Session = Depends(get_db),
) -> ProjectAutoCheckResponse:
    return run_auto_check_portfolio_project(payload, db)


@router.get("/projects/{project_id}", response_model=ProjectPortfolioItem)
def get_portfolio_project(
    project_id: int,
    db: Session = Depends(get_db),
) -> ProjectPortfolioItem:
    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return build_portfolio_item(project)


@router.get("/projects/{project_id}/step-one", response_model=ProjectStepOneResponse)
def get_project_step_one(
    project_id: int,
    db: Session = Depends(get_db),
) -> ProjectStepOneResponse:
    """Return the complete, source-aware project check without inventing values."""

    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return build_project_step_one(project)


@router.post(
    "/projects/{project_id}/traffic-snapshots",
    response_model=ProjectTrafficSnapshotResponse,
)
def save_project_traffic_snapshot(
    project_id: int,
    payload: ProjectTrafficSnapshotRequest,
    db: Session = Depends(get_db),
) -> ProjectTrafficSnapshotResponse:
    """Append a source-backed monthly traffic observation without inventing missing data."""

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    observed_at = payload.observed_at
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    else:
        observed_at = observed_at.astimezone(UTC)
    canonical = json.dumps(
        {
            "project_id": project_id,
            "metric_key": "website_traffic_monthly",
            "value": str(payload.website_traffic_monthly.normalize()),
            "source_url": payload.source_url,
            "observed_at": observed_at.isoformat(),
            "geography": payload.geography.upper(),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    source_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    snapshot = db.scalar(select(MetricSnapshot).where(MetricSnapshot.source_hash == source_hash))
    created = snapshot is None
    if snapshot is None:
        snapshot = MetricSnapshot(
            project_id=project.id,
            metric_key="website_traffic_monthly",
            numeric_value=payload.website_traffic_monthly,
            unit="visits/month",
            quality=DataQuality.IMPORTED,
            source_name=payload.source_name,
            source_url=payload.source_url,
            observed_at=observed_at,
            valid_until=observed_at + timedelta(days=45),
            confidence=0.8,
            geography=payload.geography.upper(),
            method_version="manual-or-csv-source-v1",
            source_hash=source_hash,
            payload_json={
                "change_reason": payload.note,
                "entry_type": "MANUAL_OR_CSV",
                "actor": payload.actor,
            },
        )
        db.add(snapshot)
        db.flush()
        db.add(
            AuditLog(
                entity_type="project_metric_snapshot",
                entity_id=str(snapshot.id),
                action=AuditAction.CREATE,
                actor=payload.actor,
                payload_json={
                    "project_id": project.id,
                    "metric_key": snapshot.metric_key,
                    "numeric_value": str(payload.website_traffic_monthly),
                    "unit": snapshot.unit,
                    "source_name": snapshot.source_name,
                    "source_url": snapshot.source_url,
                    "observed_at": observed_at.isoformat(),
                    "valid_until": snapshot.valid_until.isoformat(),
                    "confidence": snapshot.confidence,
                    "warning_only": True,
                    "google_ads_write": False,
                },
            )
        )
    db.commit()
    loaded = load_portfolio_project(db, project.id)
    assert loaded is not None and snapshot is not None
    return ProjectTrafficSnapshotResponse(
        snapshot_id=snapshot.id,
        created=created,
        audit_written=created,
        step_one=build_project_step_one(loaded),
    )


@router.post(
    "/projects/{project_id}/step-one-decision",
    response_model=ProjectStepOneDecisionResponse,
)
def decide_project_step_one(
    project_id: int,
    payload: ProjectStepOneDecisionRequest,
    db: Session = Depends(get_db),
) -> ProjectStepOneDecisionResponse:
    """Save the Step 1 evidence snapshot and optionally expose it in Step 2."""

    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    check = build_project_step_one(project)
    if payload.decision == "PREPARE_STEP_2" and not check.decision_ready:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Chưa đủ số liệu cốt lõi để chuyển sang Bước 2.",
                "blocking_fields": check.blocking_fields,
            },
        )

    before = {
        "stage": project.stage.value,
        "next_action": project.next_action,
    }
    if payload.decision == "PREPARE_STEP_2":
        project.stage = ProjectStage.PREP
        project.next_action = "Bước 2 · Chuẩn bị nội dung và cấu trúc campaign"
    else:
        project.stage = ProjectStage.RESEARCH
        project.next_action = "Bổ sung các nguồn còn thiếu trong Bước 1"
    after = {
        "stage": project.stage.value,
        "next_action": project.next_action,
    }
    db.add(
        AuditLog(
            entity_type="project_step_one_decision",
            entity_id=str(project.id),
            action=AuditAction.UPDATE,
            actor=payload.actor,
            payload_json={
                "decision": payload.decision,
                "before": before,
                "after": after,
                "step_one_snapshot": check.model_dump(mode="json"),
                "warning_only": True,
                "project_included": True,
                "permissions_changed": False,
                "campaign_state_changed": False,
                "google_ads_write": False,
            },
        )
    )
    db.commit()
    project = load_portfolio_project(db, project_id)
    assert project is not None
    return ProjectStepOneDecisionResponse(
        project=build_portfolio_item(project),
        decision=payload.decision,
    )


@router.get("/projects/{project_id}/truth/{metric_key}", response_model=MetricEnvelope)
def get_metric_truth(
    project_id: int,
    metric_key: str,
    db: Session = Depends(get_db),
) -> MetricEnvelope:
    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    metric = build_portfolio_item(project).metrics.get(metric_key)
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not found")
    return metric


@router.patch("/projects/{project_id}/workflow", response_model=ProjectPortfolioItem)
def update_project_workflow(
    project_id: int,
    payload: ProjectWorkflowUpdate,
    db: Session = Depends(get_db),
) -> ProjectPortfolioItem:
    project = load_portfolio_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    before = {
        "stage": project.stage.value,
        "registration_status": project.registration_status.value,
        "owner": project.owner,
        "next_action": project.next_action,
        "next_action_due_at": (
            project.next_action_due_at.isoformat() if project.next_action_due_at else None
        ),
    }
    updates = payload.model_dump(exclude_unset=True, exclude={"actor"})
    for enum_field in ("stage", "registration_status"):
        if enum_field in updates and updates[enum_field] is None:
            updates.pop(enum_field)
    for field, value in updates.items():
        setattr(project, field, value)

    after = {
        "stage": project.stage.value,
        "registration_status": project.registration_status.value,
        "owner": project.owner,
        "next_action": project.next_action,
        "next_action_due_at": (
            project.next_action_due_at.isoformat() if project.next_action_due_at else None
        ),
    }
    if before != after:
        db.add(
            AuditLog(
                entity_type="project_workflow",
                entity_id=str(project.id),
                action=AuditAction.UPDATE,
                actor=payload.actor,
                payload_json={
                    "before": before,
                    "after": after,
                    "warning_only": True,
                    "google_ads_write": False,
                },
            )
        )
    db.commit()
    project = load_portfolio_project(db, project_id)
    assert project is not None
    return build_portfolio_item(project)
