from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.models import Campaign, CampaignProgramLink, Program
from afi_os.schemas import (
    CampaignExposureRead,
    CampaignImportCommitResponse,
    CampaignImportPreview,
    CampaignProgramMapRequest,
    ExposureSummaryResponse,
    RiskAcknowledgementRequest,
)
from afi_os.services.campaign_import import analyze_campaign_import, commit_campaign_import
from afi_os.services.exposure import campaign_exposure_rows, exposure_summary

router = APIRouter(prefix="/api/exposure", tags=["exposure"])


def _public_analysis(data: dict) -> dict:
    return {key: value for key, value in data.items() if not key.startswith("_")}


def _analyze_or_422(
    db: Session,
    data: bytes,
    source: str,
    account_external_id: str,
    account_name: str,
    default_program_id: int | None,
) -> dict:
    try:
        return analyze_campaign_import(
            db,
            data,
            source,
            account_external_id,
            account_name,
            default_program_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/google-ads-import/preview", response_model=CampaignImportPreview)
async def preview_google_ads(
    file: UploadFile = File(...),
    source: str = Form(default="GOOGLE_ADS_CSV"),
    account_external_id: str = Form(default="CSV-IMPORT"),
    account_name: str = Form(default="Google Ads CSV"),
    default_program_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> CampaignImportPreview:
    analysis = _analyze_or_422(
        db,
        await file.read(),
        source,
        account_external_id,
        account_name,
        default_program_id,
    )
    return CampaignImportPreview(**_public_analysis(analysis))


@router.post("/google-ads-import/commit", response_model=CampaignImportCommitResponse)
async def commit_google_ads(
    file: UploadFile = File(...),
    source: str = Form(default="GOOGLE_ADS_CSV"),
    account_external_id: str = Form(default="CSV-IMPORT"),
    account_name: str = Form(default="Google Ads CSV"),
    default_program_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> CampaignImportCommitResponse:
    analysis = _analyze_or_422(
        db,
        await file.read(),
        source,
        account_external_id,
        account_name,
        default_program_id,
    )
    written = commit_campaign_import(db, analysis)
    return CampaignImportCommitResponse(rows_written=written, **_public_analysis(analysis))


@router.get("/summary", response_model=ExposureSummaryResponse)
def get_exposure_summary(db: Session = Depends(get_db)) -> ExposureSummaryResponse:
    return ExposureSummaryResponse(**exposure_summary(db))


def _campaign_or_404(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _campaign_read(db: Session, campaign_id: int) -> CampaignExposureRead:
    row = next(
        (item for item in campaign_exposure_rows(db) if item["campaign_id"] == campaign_id),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignExposureRead(**row)


@router.post(
    "/campaigns/{campaign_id}/acknowledge",
    response_model=CampaignExposureRead,
)
def acknowledge_campaign_risk(
    campaign_id: int,
    payload: RiskAcknowledgementRequest,
    db: Session = Depends(get_db),
) -> CampaignExposureRead:
    _campaign_or_404(db, campaign_id)
    link = db.scalar(
        select(CampaignProgramLink).where(CampaignProgramLink.campaign_id == campaign_id)
    )
    if link is None:
        link = CampaignProgramLink(campaign_id=campaign_id, link_source="MANUAL")
        db.add(link)
    link.risk_acknowledged_at = datetime.now(UTC)
    link.risk_acknowledged_by = payload.actor
    link.risk_note = payload.note
    db.commit()
    return _campaign_read(db, campaign_id)


@router.post("/campaigns/{campaign_id}/program", response_model=CampaignExposureRead)
def map_campaign_program(
    campaign_id: int,
    payload: CampaignProgramMapRequest,
    db: Session = Depends(get_db),
) -> CampaignExposureRead:
    _campaign_or_404(db, campaign_id)
    if payload.program_id is not None and db.get(Program, payload.program_id) is None:
        raise HTTPException(status_code=404, detail="Program not found")
    link = db.scalar(
        select(CampaignProgramLink).where(CampaignProgramLink.campaign_id == campaign_id)
    )
    if link is None:
        link = CampaignProgramLink(campaign_id=campaign_id, link_source="MANUAL")
        db.add(link)
    link.program_id = payload.program_id
    link.link_source = "MANUAL"
    link.risk_acknowledged_at = None
    link.risk_acknowledged_by = None
    link.risk_note = None
    db.commit()
    return _campaign_read(db, campaign_id)
