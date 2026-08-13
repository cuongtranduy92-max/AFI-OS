from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from afi_os.db import get_db
from afi_os.models import AdsAccount, Email, NurtureLog, Resource
from afi_os.schemas import (
    AdsAccountCreate,
    AdsAccountResponse,
    AdsAccountUpdate,
    EmailCreate,
    EmailResponse,
    EmailUpdate,
    NurtureCheckRequest,
    ResourceCreate,
    ResourceOverviewResponse,
    ResourceResponse,
    ResourceUpdate,
)
from afi_os.services.resource_rules import nurture_status
from afi_os.services.resources import (
    account_response,
    build_resource_overview,
    email_info,
    email_response,
    resource_response,
)

router = APIRouter(tags=["resources"])


def _email(db: Session, email_id: int) -> Email:
    item = db.scalar(
        select(Email)
        .where(Email.id == email_id)
        .options(selectinload(Email.nurture_logs))
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy email.")
    return item


def _account(db: Session, account_id: int) -> AdsAccount:
    item = db.scalar(
        select(AdsAccount)
        .where(AdsAccount.id == account_id)
        .options(
            selectinload(AdsAccount.email),
            selectinload(AdsAccount.current_project),
            selectinload(AdsAccount.camp_plan),
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản Ads.")
    return item


def _resource(db: Session, resource_id: int) -> Resource:
    item = db.get(Resource, resource_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên.")
    return item


@router.get("/api/resources/overview", response_model=ResourceOverviewResponse)
def resource_overview(
    planned_camps: int | None = Query(default=None, ge=0, le=100000),
    db: Session = Depends(get_db),
) -> ResourceOverviewResponse:
    return build_resource_overview(db, today=date.today(), planned_camps=planned_camps)


@router.get("/api/emails", response_model=list[EmailResponse])
def list_emails(db: Session = Depends(get_db)) -> list[EmailResponse]:
    return build_resource_overview(db, today=date.today()).emails


@router.post("/api/emails", response_model=EmailResponse, status_code=status.HTTP_201_CREATED)
def create_email(payload: EmailCreate, db: Session = Depends(get_db)) -> EmailResponse:
    item = Email(**payload.model_dump(exclude_none=True))
    if item.created_at is None:
        item.created_at = datetime.now(UTC)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email đã tồn tại.") from exc
    return email_response(_email(db, item.id), today=date.today())


@router.patch("/api/emails/{email_id}", response_model=EmailResponse)
def update_email(
    email_id: int, payload: EmailUpdate, db: Session = Depends(get_db)
) -> EmailResponse:
    item = _email(db, email_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key not in {"status_override", "note"}:
            continue
        setattr(item, key, value)
    db.commit()
    return email_response(_email(db, email_id), today=date.today())


@router.delete("/api/emails/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_email(email_id: int, db: Session = Depends(get_db)) -> Response:
    item = _email(db, email_id)
    if item.ads_accounts:
        raise HTTPException(status_code=409, detail="Email đang gắn tài khoản Ads; chưa thể xóa.")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/emails/{email_id}/nurture-check", response_model=EmailResponse)
def nurture_check(
    email_id: int,
    payload: NurtureCheckRequest,
    db: Session = Depends(get_db),
) -> EmailResponse:
    today = date.today()
    item = _email(db, email_id)
    suggested = set(nurture_status(email_info(item), today).tasks_today)
    unknown = [task for task in payload.tasks_done if task not in suggested]
    if unknown:
        raise HTTPException(status_code=422, detail="Chỉ được tick tác vụ hệ thống gợi ý hôm nay.")
    log = db.scalar(
        select(NurtureLog).where(NurtureLog.email_id == email_id, NurtureLog.date == today)
    )
    if log is None:
        log = NurtureLog(email_id=email_id, date=today, tasks_done=[])
        db.add(log)
    log.tasks_done = payload.tasks_done
    db.commit()
    return email_response(_email(db, email_id), today=today)


@router.get("/api/ads-accounts", response_model=list[AdsAccountResponse])
def list_ads_accounts(db: Session = Depends(get_db)) -> list[AdsAccountResponse]:
    return build_resource_overview(db, today=date.today()).ads_accounts


@router.get("/api/ads-accounts/selectable", response_model=list[AdsAccountResponse])
def list_selectable_ads_accounts(
    db: Session = Depends(get_db),
) -> list[AdsAccountResponse]:
    overview = build_resource_overview(db, today=date.today())
    return [item for item in overview.ads_accounts if item.selectable]


@router.post(
    "/api/ads-accounts",
    response_model=AdsAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ads_account(
    payload: AdsAccountCreate, db: Session = Depends(get_db)
) -> AdsAccountResponse:
    if payload.email_id is not None:
        _email(db, payload.email_id)
    external_id = payload.external_id or f"resource-{uuid4().hex[:20]}"
    item = AdsAccount(
        external_id=external_id,
        name=payload.display_name,
        display_name=payload.display_name,
        email_id=payload.email_id,
        account_type=payload.type,
        rent_cost=payload.rent_cost,
        spend_fee_pct=payload.spend_fee_pct,
        resource_state=payload.state,
        health=payload.health,
        note=payload.note,
        status="RESOURCE_TRACKING",
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mã tài khoản Ads đã tồn tại.") from exc
    return account_response(_account(db, item.id))


@router.patch("/api/ads-accounts/{account_id}", response_model=AdsAccountResponse)
def update_ads_account(
    account_id: int,
    payload: AdsAccountUpdate,
    db: Session = Depends(get_db),
) -> AdsAccountResponse:
    item = _account(db, account_id)
    values = payload.model_dump(exclude_unset=True)
    if "email_id" in values and values["email_id"] is not None:
        _email(db, values["email_id"])
    mapping = {"type": "account_type", "state": "resource_state"}
    for key, value in values.items():
        if value is None and key not in {"email_id", "note"}:
            continue
        setattr(item, mapping.get(key, key), value)
        if key == "display_name" and value:
            item.name = value
    db.commit()
    return account_response(_account(db, account_id))


@router.delete("/api/ads-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ads_account(account_id: int, db: Session = Depends(get_db)) -> Response:
    item = _account(db, account_id)
    if item.current_project_id or item.campaigns:
        raise HTTPException(
            status_code=409,
            detail="Tài khoản đang gắn dự án/campaign; chỉ được cập nhật trạng thái.",
        )
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/resources", response_model=list[ResourceResponse])
def list_resources(db: Session = Depends(get_db)) -> list[ResourceResponse]:
    return [resource_response(item) for item in db.scalars(select(Resource).order_by(Resource.id))]


@router.post(
    "/api/resources",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_resource(
    payload: ResourceCreate, db: Session = Depends(get_db)
) -> ResourceResponse:
    item = Resource(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return resource_response(item)


@router.patch("/api/resources/{resource_id}", response_model=ResourceResponse)
def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
) -> ResourceResponse:
    item = _resource(db, resource_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key not in {"owner_name", "note"}:
            continue
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return resource_response(item)


@router.delete("/api/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(resource_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_resource(db, resource_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
