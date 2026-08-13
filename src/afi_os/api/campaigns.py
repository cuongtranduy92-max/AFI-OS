from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.services.campaign_diagnosis import diagnose_all_campaigns, diagnose_one_campaign

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("/diagnoses")
def campaign_diagnoses(db: Session = Depends(get_db)) -> dict:
    return {
        "campaigns": diagnose_all_campaigns(db),
        "warning_only": True,
        "google_ads_write_operations_enabled": False,
    }


@router.get("/{campaign_id}/diagnosis")
def campaign_diagnosis(
    campaign_id: int,
    refresh: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    payload = diagnose_one_campaign(db, campaign_id, refresh_api=refresh, persist=True)
    if payload is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy campaign")
    return payload
