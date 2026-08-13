from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from afi_os.enums import AdsAccountState, CampPlanStatus
from afi_os.models import AdsAccount, CampPlan, Email, NurtureLog, Resource
from afi_os.schemas import (
    AdsAccountResponse,
    EmailResponse,
    NurtureStatusResponse,
    ResourceAlertResponse,
    ResourceOverviewResponse,
    ResourceResponse,
)
from afi_os.services.resource_rules import (
    AdsAccountInfo,
    EmailInfo,
    ResourceInfo,
    build_alerts,
    nurture_status,
    selectable_accounts,
)

RESOURCE_TYPE_ORDER = (
    "paypal",
    "payoneer",
    "wise",
    "card",
    "crypto_wallet",
    "exchange",
    "sim",
    "device",
    "website",
    "social",
)


def email_info(item: Email) -> EmailInfo:
    return EmailInfo(
        email_id=item.id,
        address=item.address,
        created_at=item.created_at,
        declared_done=item.declared_done,
        device_changes=item.device_changes,
        usage_history=tuple(item.usage_history or []),
        status_override=item.status_override,
    )


def account_info(item: AdsAccount) -> AdsAccountInfo:
    return AdsAccountInfo(
        account_id=item.id,
        email_id=item.email_id,
        project_ids=(item.current_project_id,) if item.current_project_id else (),
        state=item.resource_state.value,
        display_name=item.display_name or item.name,
    )


def resource_info(item: Resource) -> ResourceInfo:
    return ResourceInfo(
        resource_id=item.id,
        type=item.type,
        label=item.label,
        monthly_in_usd=float(item.monthly_in_usd or 0),
        linked_gateways=tuple(item.linked_gateways or []),
        owner_name=item.owner_name,
    )


def _email_query() -> Select[tuple[Email]]:
    return select(Email).options(selectinload(Email.nurture_logs)).order_by(Email.created_at)


def load_resource_inputs(
    db: Session,
) -> tuple[list[Email], list[AdsAccount], list[Resource]]:
    emails = list(db.scalars(_email_query()).unique())
    accounts = list(
        db.scalars(
            select(AdsAccount)
            .options(
                selectinload(AdsAccount.email),
                selectinload(AdsAccount.current_project),
                selectinload(AdsAccount.camp_plan),
            )
            .order_by(AdsAccount.id)
        ).unique()
    )
    resources = list(db.scalars(select(Resource).order_by(Resource.type, Resource.label)))
    return emails, accounts, resources


def _today_log(item: Email, today: date) -> NurtureLog | None:
    return next((log for log in item.nurture_logs if log.date == today), None)


def email_response(item: Email, *, today: date) -> EmailResponse:
    status = nurture_status(email_info(item), today)
    today_log = _today_log(item, today)
    return EmailResponse(
        id=item.id,
        address=item.address,
        source=item.source,
        created_at=item.created_at,
        declared_done=item.declared_done,
        device_changes=item.device_changes,
        usage_history=list(item.usage_history or []),
        status_override=item.status_override,
        note=item.note,
        nurture_status=NurtureStatusResponse(
            stage=status.stage,
            age_days=status.age_days,
            chin_eta_days=status.chin_eta_days,
            is_chin=status.is_chin,
            is_dirty=status.is_dirty,
            tasks_today=list(status.tasks_today),
            tasks_done=list(today_log.tasks_done or []) if today_log else [],
        ),
    )


def account_response(
    item: AdsAccount,
    *,
    selectable_ids: set[int] | None = None,
) -> AdsAccountResponse:
    return AdsAccountResponse(
        id=item.id,
        external_id=item.external_id,
        email_id=item.email_id,
        email_address=item.email.address if item.email else None,
        type=item.account_type,
        display_name=item.display_name or item.name,
        rent_cost=Decimal(item.rent_cost or 0),
        spend_fee_pct=Decimal(item.spend_fee_pct or 0),
        state=item.resource_state,
        health=item.health,
        current_project_id=item.current_project_id,
        current_project_domain=item.current_project.domain if item.current_project else None,
        camp_plan_id=item.camp_plan.id if item.camp_plan else None,
        camp_plan_status=item.camp_plan.status if item.camp_plan else None,
        note=item.note,
        selectable=item.id in (selectable_ids or set()),
    )


def resource_response(item: Resource) -> ResourceResponse:
    return ResourceResponse(
        id=item.id,
        type=item.type,
        label=item.label,
        monthly_in_usd=Decimal(item.monthly_in_usd or 0),
        linked_gateways=list(item.linked_gateways or []),
        owner_name=item.owner_name,
        note=item.note,
    )


def count_planned_camps(db: Session, *, today: date) -> int:
    month_start = datetime(today.year, today.month, 1, tzinfo=UTC)
    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(today.year, today.month + 1, 1, tzinfo=UTC)
    return int(
        db.scalar(
            select(func.count(CampPlan.id)).where(
                CampPlan.status.in_((CampPlanStatus.DRAFT, CampPlanStatus.DEPLOYED)),
                CampPlan.created_at >= month_start,
                CampPlan.created_at < next_month,
            )
        )
        or 0
    )


def build_resource_overview(
    db: Session,
    *,
    today: date,
    planned_camps: int | None = None,
) -> ResourceOverviewResponse:
    emails, accounts, resources = load_resource_inputs(db)
    email_inputs = [email_info(item) for item in emails]
    account_inputs = [account_info(item) for item in accounts]
    resource_inputs = [resource_info(item) for item in resources]
    planned = count_planned_camps(db, today=today) if planned_camps is None else planned_camps
    selectable_ids = set(selectable_accounts(email_inputs, account_inputs, today))
    statuses = [nurture_status(item, today) for item in email_inputs]
    alerts = build_alerts(email_inputs, account_inputs, resource_inputs, planned, today)
    type_counts = {resource_type: 0 for resource_type in RESOURCE_TYPE_ORDER}
    for item in resources:
        type_counts[item.type] = type_counts.get(item.type, 0) + 1
    return ResourceOverviewResponse(
        planned_camps_this_month=planned,
        planned_camps_source="database" if planned_camps is None else "manual",
        kpis={
            "chin": sum(status.is_chin and not status.is_dirty for status in statuses),
            "nurturing": sum(not status.is_chin for status in statuses),
            "dirty": sum(status.is_dirty for status in statuses),
            "accounts_ready": len(selectable_ids),
        },
        type_counts=type_counts,
        alerts=[
            ResourceAlertResponse(
                level=item.level,
                code=item.code,
                subject=item.subject,
                message=item.message,
            )
            for item in alerts
        ],
        emails=[email_response(item, today=today) for item in emails],
        ads_accounts=[
            account_response(item, selectable_ids=selectable_ids) for item in accounts
        ],
        resources=[resource_response(item) for item in resources],
        selectable_account_ids=sorted(selectable_ids),
        stores_passwords=False,
    )


def account_is_selectable(
    db: Session,
    account: AdsAccount,
    *,
    project_id: int | None = None,
    today: date,
) -> bool:
    if project_id and account.current_project_id == project_id:
        if account.email is None or account.resource_state not in {
            AdsAccountState.READY,
            AdsAccountState.CHON_DU_AN,
            AdsAccountState.CHAY,
        }:
            return False
        status = nurture_status(email_info(account.email), today)
        return status.is_chin and not status.is_dirty and account.email.status_override != "LOCKED"
    emails, accounts, _ = load_resource_inputs(db)
    selectable_ids = selectable_accounts(
        [email_info(item) for item in emails],
        [account_info(item) for item in accounts],
        today,
    )
    return account.id in selectable_ids
