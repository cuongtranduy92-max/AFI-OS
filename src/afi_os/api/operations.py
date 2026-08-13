from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.schemas import (
    GoogleAdsReadinessResponse,
    OperationsInboxResponse,
    RuntimeStatusResponse,
)
from afi_os.services.google_ads_readiness import google_ads_readiness
from afi_os.services.operations import operations_inbox
from afi_os.services.runtime_status import runtime_status

router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/inbox", response_model=OperationsInboxResponse)
def get_operations_inbox(db: Session = Depends(get_db)) -> OperationsInboxResponse:
    return OperationsInboxResponse(**operations_inbox(db))


@router.get("/runtime-status", response_model=RuntimeStatusResponse)
def get_runtime_status(db: Session = Depends(get_db)) -> RuntimeStatusResponse:
    return RuntimeStatusResponse(**runtime_status(db))


@router.get("/google-ads-readiness", response_model=GoogleAdsReadinessResponse)
def get_google_ads_readiness(
    db: Session = Depends(get_db),
) -> GoogleAdsReadinessResponse:
    return GoogleAdsReadinessResponse(**google_ads_readiness(db))
