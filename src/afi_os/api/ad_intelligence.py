from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from afi_os.db import get_db
from afi_os.enums import (
    AppraisalJobStatus,
    AuditAction,
    CaptureStatus,
    ProjectStage,
    RegistrationStatus,
    WatchStatus,
)
from afi_os.models import (
    AdObservation,
    Advertiser,
    AppraisalJob,
    AuditLog,
    Project,
    RawCapture,
)
from afi_os.schemas import (
    AdvertiserCreate,
    AdvertiserExpandRequest,
    AdvertiserExpansionResponse,
    AdvertiserProjectLink,
    AdvertiserProjectsResponse,
    AdvertiserProviderStatusResponse,
    AdvertiserRead,
    AdvertiserSnapshotImport,
    AdvertiserSnapshotImportResponse,
    AdvertiserWatchRequest,
    DiscoveredDomainQueueRequest,
    GraphEdge,
    GraphNode,
    GraphResponse,
    ProjectAdvertiserLink,
    ProjectAdvertisersResponse,
    ProjectCreate,
    ProjectNetworkAdvertiser,
    ProjectNetworkResponse,
    ProjectRadarItem,
    ProjectRead,
    RawCaptureCreate,
    RawCaptureRead,
    RawCaptureReviewItem,
    RawCaptureReviewRequest,
)
from afi_os.services.ad_intelligence import AdvertiserScoreInput, independent_advertiser_score
from afi_os.services.advertiser_provider import (
    AdvertiserProviderError,
    expand_advertisers,
    provider_status,
    quota_status,
)

router = APIRouter(prefix="/api/ad-intelligence", tags=["ad-intelligence"])

PENDING_CAPTURE_STATUSES = (CaptureStatus.RAW, CaptureStatus.NEEDS_REVIEW)
CAPTURE_IDENTITY_VERSION = "capture-v2"
CAPTURE_IDENTITY_NAMESPACE = "afi-os-local:capture-intake"
IDEMPOTENCY_KEY_MAX_LENGTH = 200
ADVERTISER_SNAPSHOT_VERSION = "advertiser-snapshot-v1"


def _relationship_summary(items: list[AdObservation]) -> dict[str, Any]:
    ordered = sorted(
        items,
        key=lambda item: (
            item.snapshot_date,
            _utc(item.created_at) or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    reported_ads = next(
        (
            int(item.metadata_json["reported_ad_count"])
            for item in ordered
            if (item.metadata_json or {}).get("reported_ad_count") is not None
        ),
        None,
    )
    first_seen = [_utc(item.first_seen_at) for item in items if item.first_seen_at]
    last_seen = [_utc(item.last_seen_at) for item in items if item.last_seen_at]
    observed: list[datetime] = []
    for item in items:
        checked_at = (item.metadata_json or {}).get("checked_at")
        parsed_checked_at: datetime | None = None
        if isinstance(checked_at, str):
            try:
                parsed = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                parsed_checked_at = _utc(parsed) or parsed
            except ValueError:
                pass
        if parsed_checked_at is not None:
            observed.append(parsed_checked_at)
        else:
            created_at = _utc(item.created_at)
            if created_at is not None:
                observed.append(created_at)
    source_urls = sorted({item.source_url for item in items if item.source_url})
    return {
        "observation_count": len(items),
        "reported_ads": reported_ads,
        "observed_at": max(observed) if observed else None,
        "first_seen_at": min(first_seen) if first_seen else None,
        "last_seen_at": max(last_seen) if last_seen else None,
        "source_urls": source_urls[:10],
        "source_count": len(source_urls),
    }


def _capture_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").removeprefix("www.")
    return host or None


def _hash(*parts: str | None) -> str:
    joined = "\n".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = _utc(value) or value
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise HTTPException(status_code=422, detail="metadata keys must be strings")
        return {key: _canonical_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(status_code=422, detail="capture data must contain finite numbers")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise HTTPException(status_code=422, detail="capture data must be JSON-compatible")


def _capture_fingerprint(payload: RawCaptureCreate) -> str:
    canonical = _canonical_json_value(payload.model_dump(mode="python"))
    try:
        serialized = json.dumps(
            canonical,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="capture data must be JSON-compatible") from exc
    return _hash(CAPTURE_IDENTITY_VERSION, "fingerprint", serialized)


def _normalize_idempotency_key(request: Request, header_value: str | None) -> str | None:
    raw_values = request.headers.getlist("idempotency-key")
    if len(raw_values) > 1:
        raise HTTPException(status_code=422, detail="Idempotency-Key must be sent only once")
    if header_value is None:
        return None
    key = header_value.strip()
    if not key:
        raise HTTPException(status_code=422, detail="Idempotency-Key cannot be blank")
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Idempotency-Key cannot exceed {IDEMPOTENCY_KEY_MAX_LENGTH} characters",
        )
    if "," in key or any(ord(character) < 0x21 or ord(character) == 0x7F for character in key):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must contain one visible token without spaces or commas",
        )
    return key


def _capture_identity(
    payload: RawCaptureCreate,
    idempotency_key: str | None,
) -> dict[str, str]:
    fingerprint = _capture_fingerprint(payload)
    identity = {
        "version": CAPTURE_IDENTITY_VERSION,
        "mode": "CONTENT",
        "namespace": CAPTURE_IDENTITY_NAMESPACE,
        "fingerprint": fingerprint,
    }
    if idempotency_key is None:
        return identity
    key_hash = _hash(
        CAPTURE_IDENTITY_VERSION,
        "idempotency-key",
        CAPTURE_IDENTITY_NAMESPACE,
        idempotency_key,
    )
    identity.update({"mode": "IDEMPOTENCY_KEY", "key_hash": key_hash})
    return identity


def _legacy_capture_hash(payload: RawCaptureCreate) -> str:
    """Keep the 0.2.83 no-header hash as the first compatibility bucket."""

    return _hash(
        payload.source_url,
        payload.selected_text,
        payload.visible_text,
        payload.advertiser_name,
        payload.project_domain,
        payload.headline,
        payload.description,
        str(payload.snapshot_date),
    )


def _capture_hashes(
    canonical_payload: RawCaptureCreate,
    identity: dict[str, str],
) -> tuple[str, str | None]:
    if identity["mode"] == "IDEMPOTENCY_KEY":
        return (
            _hash(
                CAPTURE_IDENTITY_VERSION,
                "keyed-capture",
                CAPTURE_IDENTITY_NAMESPACE,
                identity["key_hash"],
            ),
            None,
        )
    legacy_hash = _legacy_capture_hash(canonical_payload)
    correction_hash = _hash(
        CAPTURE_IDENTITY_VERSION,
        "content-correction",
        legacy_hash,
        identity["fingerprint"],
    )
    return legacy_hash, correction_hash


def _legacy_capture_matches(
    capture: RawCapture,
    canonical_payload: RawCaptureCreate,
) -> bool:
    stored_payload = dict(capture.parsed_payload or {})
    for reserved in ("capture_identity", "materialization", "review"):
        stored_payload.pop(reserved, None)
    stored_payload.update(
        {
            "source_url": capture.source_url,
            "page_title": capture.page_title,
            "selected_text": capture.selected_text,
            "visible_text": capture.visible_text,
        }
    )
    allowed_fields = RawCaptureCreate.model_fields.keys()
    try:
        stored = RawCaptureCreate.model_validate(
            {key: value for key, value in stored_payload.items() if key in allowed_fields}
        )
    except ValueError:
        return False
    if stored.snapshot_date is None:
        captured_at = _utc(capture.captured_at) or _capture_now()
        stored = stored.model_copy(update={"snapshot_date": captured_at.date()})
    return _capture_fingerprint(stored) == _capture_fingerprint(canonical_payload)


def _resolve_existing_capture(
    capture: RawCapture,
    requested_identity: dict[str, str],
    canonical_payload: RawCaptureCreate,
) -> RawCapture | None:
    stored_identity = (capture.parsed_payload or {}).get("capture_identity")
    if not isinstance(stored_identity, dict):
        if requested_identity["mode"] == "CONTENT" and _legacy_capture_matches(
            capture, canonical_payload
        ):
            return capture
        return None
    comparable_fields = {"version", "mode", "namespace", "fingerprint", "key_hash"}
    if any(
        stored_identity.get(field) != requested_identity.get(field)
        for field in comparable_fields
    ):
        if requested_identity["mode"] == "IDEMPOTENCY_KEY":
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used for different capture content",
            )
        return None
    return capture


def _audit(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: AuditAction,
    payload: dict,
    *,
    actor: str = "local-user",
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            payload_json=payload,
        )
    )


def _materialize_capture(
    db: Session,
    capture: RawCapture,
    payload: RawCaptureCreate,
) -> tuple[AdObservation, bool]:
    if not payload.advertiser_name or not payload.project_domain:
        raise HTTPException(
            status_code=422,
            detail="advertiser_name and project_domain are required to accept a capture",
        )

    captured_at = _utc(capture.captured_at) or datetime.now(UTC)
    advertiser = db.scalar(
        select(Advertiser).where(
            Advertiser.verified_name == payload.advertiser_name,
            Advertiser.verified_location == payload.advertiser_location,
        )
    )
    if advertiser is None:
        advertiser = Advertiser(
            verified_name=payload.advertiser_name,
            verified_location=payload.advertiser_location,
            source_url=capture.source_url,
            first_seen_at=_utc(payload.first_seen_at) or captured_at,
            last_seen_at=_utc(payload.last_seen_at) or captured_at,
        )
        db.add(advertiser)
        db.flush()
    else:
        advertiser.first_seen_at = min(
            filter(
                None,
                [
                    _utc(advertiser.first_seen_at),
                    _utc(payload.first_seen_at),
                    captured_at,
                ],
            )
        )
        advertiser.last_seen_at = max(
            filter(
                None,
                [
                    _utc(advertiser.last_seen_at),
                    _utc(payload.last_seen_at),
                    captured_at,
                ],
            )
        )

    domain = _normalize_domain(payload.project_domain)
    if not domain:
        raise HTTPException(status_code=422, detail="project_domain is invalid")
    project = db.scalar(select(Project).where(Project.domain == domain))
    if project is None:
        project = Project(
            domain=domain,
            brand_name=payload.brand_name or domain.split(".")[0],
            category=payload.category,
            first_seen_at=_utc(payload.first_seen_at) or captured_at,
            last_seen_at=_utc(payload.last_seen_at) or captured_at,
        )
        db.add(project)
        db.flush()
    else:
        project.first_seen_at = min(
            filter(
                None,
                [
                    _utc(project.first_seen_at),
                    _utc(payload.first_seen_at),
                    captured_at,
                ],
            )
        )
        project.last_seen_at = max(
            filter(
                None,
                [_utc(project.last_seen_at), _utc(payload.last_seen_at), captured_at],
            )
        )
        if payload.category and not project.category:
            project.category = payload.category

    observation_hash = _hash(
        payload.headline,
        payload.description,
        payload.display_url,
        payload.landing_domain,
        capture.source_url,
    )
    snapshot_date = payload.snapshot_date or captured_at.date()
    existing_observation = db.scalar(
        select(AdObservation).where(
            AdObservation.advertiser_id == advertiser.id,
            AdObservation.project_id == project.id,
            AdObservation.content_hash == observation_hash,
            AdObservation.snapshot_date == snapshot_date,
        )
    )
    if existing_observation is None:
        observation = AdObservation(
            advertiser_id=advertiser.id,
            project_id=project.id,
            raw_capture_id=capture.id,
            source_url=capture.source_url,
            ad_format=payload.ad_format,
            headline=payload.headline,
            description=payload.description,
            display_url=payload.display_url,
            landing_domain=_normalize_domain(payload.landing_domain),
            country=payload.country.upper() if payload.country else None,
            language=payload.language,
            first_seen_at=_utc(payload.first_seen_at),
            last_seen_at=_utc(payload.last_seen_at),
            snapshot_date=snapshot_date,
            content_hash=observation_hash,
            metadata_json=payload.metadata,
        )
        db.add(observation)
        db.flush()
        return observation, True
    return existing_observation, False


def _advertiser_snapshot_result(
    capture: RawCapture,
    *,
    duplicate: bool,
) -> AdvertiserSnapshotImportResponse:
    materialization = (capture.parsed_payload or {}).get("materialization", {})
    return AdvertiserSnapshotImportResponse(
        capture_id=capture.id,
        project_id=int(materialization["project_id"]),
        duplicate=duplicate,
        advertisers_created=int(materialization.get("advertisers_created", 0)),
        observations_created=int(materialization.get("observations_created", 0)),
        advertisers_in_snapshot=int(materialization.get("advertisers_in_snapshot", 0)),
        reported_ads=int(materialization.get("reported_ads", 0)),
    )


@router.post(
    "/advertiser-snapshots",
    response_model=AdvertiserSnapshotImportResponse,
)
def import_advertiser_snapshot(
    payload: AdvertiserSnapshotImport,
    db: Session = Depends(get_db),
) -> AdvertiserSnapshotImportResponse:
    """Import one bounded advertiser result set with exact source provenance.

    This creates advertiser/project observations only. It deliberately does not
    infer 30-day activity, change PPC permissions, or perform Google Ads writes.
    """

    project = db.scalar(select(Project).where(Project.domain == payload.project_domain))
    if project is None:
        raise HTTPException(status_code=404, detail="project_domain is not in AFI-OS")

    identities: set[str] = set()
    canonical_candidates: list[dict[str, object]] = []
    for candidate in payload.advertisers:
        identity = candidate.external_key or (
            f"name:{candidate.advertiser_name.casefold()}|"
            f"location:{(candidate.advertiser_location or '').casefold()}"
        )
        if identity in identities:
            raise HTTPException(
                status_code=422,
                detail=f"duplicate advertiser identity in snapshot: {identity}",
            )
        identities.add(identity)
        canonical_candidates.append(candidate.model_dump(mode="json"))

    canonical_candidates.sort(
        key=lambda item: (
            str(item.get("external_key") or ""),
            str(item.get("advertiser_name") or "").casefold(),
        )
    )
    capture_hash = _hash(
        ADVERTISER_SNAPSHOT_VERSION,
        payload.project_domain,
        payload.source_url,
        payload.checked_at.astimezone(UTC).isoformat(),
        json.dumps(canonical_candidates, ensure_ascii=False, sort_keys=True),
    )
    existing_capture = db.scalar(
        select(RawCapture).where(RawCapture.capture_hash == capture_hash)
    )
    if existing_capture is not None:
        if (existing_capture.parsed_payload or {}).get("snapshot_version") != (
            ADVERTISER_SNAPSHOT_VERSION
        ):
            raise HTTPException(status_code=409, detail="capture identity collision")
        return _advertiser_snapshot_result(existing_capture, duplicate=True)

    capture = RawCapture(
        source_url=payload.source_url,
        page_title=f"{payload.source_name} · {payload.project_domain}",
        selected_text=payload.evidence_excerpt,
        visible_text=None,
        captured_at=payload.checked_at,
        status=CaptureStatus.PARSED,
        parser_version=ADVERTISER_SNAPSHOT_VERSION,
        parsed_payload={
            "snapshot_version": ADVERTISER_SNAPSHOT_VERSION,
            "project_domain": payload.project_domain,
            "source_name": payload.source_name,
            "checked_at": payload.checked_at.isoformat(),
            "evidence_excerpt": payload.evidence_excerpt,
            "geography": payload.geography,
            "language": payload.language,
            "result_set_complete": payload.result_set_complete,
            "confidence": payload.confidence,
            "advertisers": canonical_candidates,
        },
        capture_hash=capture_hash,
    )
    db.add(capture)
    db.flush()

    advertisers_created = 0
    observations_created = 0
    reported_ads = 0
    observed_date = payload.checked_at.astimezone(UTC).date()
    for candidate in payload.advertisers:
        advertiser = None
        if candidate.external_key:
            advertiser = db.scalar(
                select(Advertiser).where(Advertiser.external_key == candidate.external_key)
            )
        if advertiser is None:
            advertiser = db.scalar(
                select(Advertiser).where(
                    Advertiser.verified_name == candidate.advertiser_name,
                    Advertiser.verified_location == candidate.advertiser_location,
                )
            )
        if advertiser is None:
            advertiser = Advertiser(
                external_key=candidate.external_key,
                verified_name=candidate.advertiser_name,
                verified_location=candidate.advertiser_location,
                confidence=payload.confidence,
                source_url=candidate.advertiser_url or payload.source_url,
                first_seen_at=payload.checked_at,
                last_seen_at=None,
                notes=(
                    "Imported from a bounded advertiser result set; activity dates "
                    "remain unknown until creative-level evidence is collected."
                ),
            )
            db.add(advertiser)
            db.flush()
            advertisers_created += 1
        else:
            if candidate.external_key and advertiser.external_key is None:
                advertiser.external_key = candidate.external_key
            advertiser.confidence = max(advertiser.confidence, payload.confidence)
            if advertiser.source_url is None:
                advertiser.source_url = candidate.advertiser_url or payload.source_url

        reported_ads += candidate.reported_ad_count or 0
        content_hash = _hash(
            ADVERTISER_SNAPSHOT_VERSION,
            candidate.external_key or candidate.advertiser_name.casefold(),
            payload.project_domain,
            payload.source_url,
            observed_date.isoformat(),
        )
        observation = db.scalar(
            select(AdObservation).where(
                AdObservation.advertiser_id == advertiser.id,
                AdObservation.project_id == project.id,
                AdObservation.content_hash == content_hash,
                AdObservation.snapshot_date == observed_date,
            )
        )
        if observation is None:
            observation = AdObservation(
                advertiser_id=advertiser.id,
                project_id=project.id,
                raw_capture_id=capture.id,
                source_url=candidate.advertiser_url or payload.source_url,
                first_seen_at=None,
                last_seen_at=None,
                snapshot_date=observed_date,
                content_hash=content_hash,
                metadata_json={
                    "evidence_type": "ADVERTISER_RESULT_SET",
                    "source_name": payload.source_name,
                    "source_url": payload.source_url,
                    "source_authority": "THIRD_PARTY",
                    "checked_at": payload.checked_at.isoformat(),
                    "evidence_excerpt": payload.evidence_excerpt,
                    "external_key": candidate.external_key,
                    "reported_ad_count": candidate.reported_ad_count,
                    "result_set_complete": payload.result_set_complete,
                    "confidence": payload.confidence,
                    "geography": payload.geography,
                    "language": payload.language,
                    "activity_window_verified": False,
                },
            )
            db.add(observation)
            db.flush()
            observations_created += 1

    materialization = {
        "project_id": project.id,
        "advertisers_created": advertisers_created,
        "observations_created": observations_created,
        "advertisers_in_snapshot": len(payload.advertisers),
        "reported_ads": reported_ads,
    }
    capture.parsed_payload = {
        **capture.parsed_payload,
        "materialization": materialization,
    }
    _audit(
        db,
        "advertiser_snapshot",
        str(capture.id),
        AuditAction.IMPORT,
        {
            **materialization,
            "project_domain": payload.project_domain,
            "source_url": payload.source_url,
            "source_name": payload.source_name,
            "checked_at": payload.checked_at.isoformat(),
            "result_set_complete": payload.result_set_complete,
            "confidence": payload.confidence,
            "warning_only": True,
            "permissions_changed": False,
            "campaign_state_changed": False,
            "google_ads_write": False,
        },
        actor=payload.actor,
    )
    db.commit()
    db.refresh(capture)
    return _advertiser_snapshot_result(capture, duplicate=False)


def _claim_capture_review(
    db: Session,
    capture_id: int,
    status: CaptureStatus,
) -> bool:
    """Atomically claim a pending, unmaterialized capture for one terminal decision."""

    result = db.execute(
        update(RawCapture)
        .where(
            RawCapture.id == capture_id,
            RawCapture.status.in_(PENDING_CAPTURE_STATUSES),
            ~select(AdObservation.id)
            .where(AdObservation.raw_capture_id == RawCapture.id)
            .exists(),
        )
        .values(status=status)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _reload_capture_after_failed_claim(db: Session, capture_id: int) -> RawCapture:
    db.rollback()
    capture = db.get(RawCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="capture not found")
    if capture.status in PENDING_CAPTURE_STATUSES:
        has_observation = db.scalar(
            select(AdObservation.id).where(AdObservation.raw_capture_id == capture_id).limit(1)
        )
        if has_observation is not None:
            raise HTTPException(
                status_code=409,
                detail="capture already has a materialized observation",
            )
        raise HTTPException(status_code=409, detail="capture review is already in progress")
    return capture


def _accepted_capture_is_idempotent(
    capture: RawCapture,
    payload: RawCaptureReviewRequest,
) -> bool:
    if capture.status != CaptureStatus.PARSED:
        return False
    stored_payload = capture.parsed_payload or {}
    stored_review = stored_payload.get("review", {})
    if stored_review.get("action") != "ACCEPT":
        raise HTTPException(status_code=409, detail="parsed capture is not in the review queue")
    for field in (
        "advertiser_name",
        "advertiser_location",
        "project_domain",
        "brand_name",
        "category",
        "ad_format",
        "headline",
        "description",
        "display_url",
        "landing_domain",
        "country",
        "language",
        "first_seen_at",
        "last_seen_at",
        "snapshot_date",
    ):
        if field in payload.model_fields_set:
            requested = payload.model_dump(mode="json").get(field)
            if stored_payload.get(field) != requested:
                raise HTTPException(
                    status_code=409,
                    detail="accepted capture cannot be reviewed again with different fields",
                )
    if "metadata" in payload.model_fields_set and payload.metadata is not None:
        stored_metadata = stored_payload.get("metadata", {})
        if not isinstance(stored_metadata, dict) or any(
            stored_metadata.get(key) != value for key, value in payload.metadata.items()
        ):
            raise HTTPException(
                status_code=409,
                detail="accepted capture cannot be reviewed again with different metadata",
            )
    return True


def _rejected_capture_is_idempotent(
    capture: RawCapture,
    reason: str,
) -> bool:
    if capture.status != CaptureStatus.REJECTED:
        return False
    stored_review = (capture.parsed_payload or {}).get("review", {})
    if stored_review.get("action") != "REJECT" or stored_review.get("reason") != reason:
        raise HTTPException(
            status_code=409,
            detail="rejected capture cannot be reviewed again with a different decision",
        )
    return True


@router.post("/advertisers", response_model=AdvertiserRead)
def create_advertiser(payload: AdvertiserCreate, db: Session = Depends(get_db)) -> Advertiser:
    advertiser = Advertiser(**payload.model_dump())
    db.add(advertiser)
    db.flush()
    _audit(
        db, "Advertiser", str(advertiser.id), AuditAction.CREATE, payload.model_dump(mode="json")
    )
    db.commit()
    db.refresh(advertiser)
    return advertiser


@router.get("/advertisers", response_model=list[AdvertiserRead])
def list_advertisers(
    limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)
) -> list[Advertiser]:
    return list(
        db.scalars(select(Advertiser).order_by(Advertiser.last_seen_at.desc()).limit(limit))
    )


@router.get(
    "/provider-status", response_model=AdvertiserProviderStatusResponse
)
def advertiser_source_status(
    db: Session = Depends(get_db),
) -> AdvertiserProviderStatusResponse:
    return AdvertiserProviderStatusResponse.model_validate(provider_status(db))


@router.get("/watchlist", response_model=list[AdvertiserRead])
def advertiser_watchlist(db: Session = Depends(get_db)) -> list[Advertiser]:
    return list(
        db.scalars(
            select(Advertiser)
            .where(Advertiser.is_watchlisted.is_(True))
            .order_by(Advertiser.is_goldmine.desc(), Advertiser.verified_name.asc())
        ).all()
    )


@router.post(
    "/advertisers/expand", response_model=AdvertiserExpansionResponse
)
def expand_advertiser_domains(
    payload: AdvertiserExpandRequest,
    db: Session = Depends(get_db),
) -> AdvertiserExpansionResponse:
    try:
        result = expand_advertisers(
            db,
            payload.advertiser_ids,
            force_refresh=payload.force_refresh,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdvertiserProviderError as exc:
        code = 429 if exc.status in {"QUOTA_EXHAUSTED", "RATE_LIMITED"} else 503
        raise HTTPException(
            status_code=code,
            detail={"status": exc.status, "message": exc.detail},
        ) from exc
    return AdvertiserExpansionResponse.model_validate(
        {**result, "quota": quota_status(db)}
    )


@router.post("/advertisers/{advertiser_id}/watch", response_model=AdvertiserRead)
def update_advertiser_watchlist(
    advertiser_id: int,
    payload: AdvertiserWatchRequest,
    db: Session = Depends(get_db),
) -> Advertiser:
    advertiser = db.get(Advertiser, advertiser_id)
    if advertiser is None:
        raise HTTPException(status_code=404, detail="advertiser not found")
    advertiser.is_watchlisted = payload.watch
    _audit(
        db,
        "Advertiser",
        str(advertiser.id),
        AuditAction.UPDATE,
        {
            "is_watchlisted": payload.watch,
            "automatic_scan": False,
            "google_ads_write": False,
        },
    )
    db.commit()
    db.refresh(advertiser)
    return advertiser


@router.post("/discovered-domains/queue", response_model=dict)
def queue_discovered_domain(
    payload: DiscoveredDomainQueueRequest,
    db: Session = Depends(get_db),
) -> dict:
    advertiser = db.get(Advertiser, payload.advertiser_id)
    if advertiser is None:
        raise HTTPException(status_code=404, detail="advertiser not found")
    project = db.scalar(select(Project).where(Project.domain == payload.domain))
    created = project is None
    if project is None:
        now = datetime.now(UTC)
        project = Project(
            domain=payload.domain,
            brand_name=payload.domain.split(".", 1)[0].replace("-", " ").title(),
            affiliate_program_found=False,
            watch_status=WatchStatus.NEW,
            stage=ProjectStage.DISCOVERED,
            registration_status=RegistrationStatus.NOT_STARTED,
            next_action="DISCOVERED · Chờ người vận hành chạy kiểm tra Bước 1",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(project)
        db.flush()
    existing_job = db.scalar(
        select(AppraisalJob).where(
            AppraisalJob.project_id == project.id,
            AppraisalJob.status == AppraisalJobStatus.QUEUED,
        )
    )
    if existing_job is None:
        existing_job = AppraisalJob(
            project_id=project.id,
            domain=project.domain,
            status=AppraisalJobStatus.QUEUED,
            per_source_json={},
            force_refresh=False,
        )
        db.add(existing_job)
        db.flush()
    content_hash = _hash(
        "SERPAPI_DISCOVERY_QUEUE", str(advertiser.id), str(project.id)
    )
    observation = db.scalar(
        select(AdObservation).where(
            AdObservation.advertiser_id == advertiser.id,
            AdObservation.project_id == project.id,
            AdObservation.content_hash == content_hash,
            AdObservation.snapshot_date == datetime.now(UTC).date(),
        )
    )
    if observation is None:
        db.add(
            AdObservation(
                advertiser_id=advertiser.id,
                project_id=project.id,
                source_url=advertiser.source_url or "https://adstransparency.google.com/",
                landing_domain=project.domain,
                snapshot_date=datetime.now(UTC).date(),
                content_hash=content_hash,
                metadata_json={
                    "evidence_type": "SERPAPI_EXPANSION_DISCOVERY",
                    "source_name": "SerpApi Google Ads Transparency Center",
                    "result_set_complete": False,
                    "confidence": 0.8,
                    "queued_only": True,
                    "auto_started": False,
                },
            )
        )
    _audit(
        db,
        "project_discovery",
        str(project.id),
        AuditAction.CREATE if created else AuditAction.UPDATE,
        {
            "domain": project.domain,
            "discovered_by_advertiser_id": advertiser.id,
            "appraisal_job_id": existing_job.id,
            "auto_started": False,
            "google_ads_write": False,
        },
    )
    db.commit()
    return {
        "project_id": project.id,
        "domain": project.domain,
        "project_state": "DISCOVERED",
        "job_id": existing_job.id,
        "job_status": "QUEUED",
        "created": created,
        "auto_started": False,
        "message": "Đã đưa vào hàng đợi; chỉ chạy khi anh mở dự án hoặc bấm kiểm tra.",
    }


@router.post("/projects", response_model=ProjectRead)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    existing = db.scalar(select(Project).where(Project.domain == payload.domain))
    if existing:
        return existing
    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    _audit(db, "Project", str(project.id), AuditAction.CREATE, payload.model_dump(mode="json"))
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)
) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.last_seen_at.desc()).limit(limit)))


@router.get("/projects/{project_id}/advertisers", response_model=ProjectAdvertisersResponse)
def project_advertisers(
    project_id: int, db: Session = Depends(get_db)
) -> ProjectAdvertisersResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    observations = list(
        db.scalars(select(AdObservation).where(AdObservation.project_id == project_id))
    )
    grouped: dict[int, list[AdObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.advertiser_id].append(observation)
    advertisers = {
        advertiser.id: advertiser
        for advertiser in db.scalars(
            select(Advertiser).where(Advertiser.id.in_(list(grouped)))
        )
    } if grouped else {}
    related_counts: Counter[int] = Counter()
    if grouped:
        for advertiser_id, related_project_id in db.execute(
            select(AdObservation.advertiser_id, AdObservation.project_id)
            .where(AdObservation.advertiser_id.in_(list(grouped)))
            .distinct()
        ):
            if related_project_id is not None:
                related_counts[advertiser_id] += 1
    links: list[ProjectAdvertiserLink] = []
    for advertiser_id, items in grouped.items():
        advertiser = advertisers.get(advertiser_id)
        if advertiser is None:
            continue
        summary = _relationship_summary(items)
        links.append(
            ProjectAdvertiserLink(
                advertiser_id=advertiser.id,
                advertiser_name=advertiser.verified_name,
                advertiser_location=advertiser.verified_location,
                classification=advertiser.classification,
                confidence=advertiser.confidence,
                related_project_count=max(1, related_counts[advertiser.id]),
                domain_count=advertiser.domain_count,
                is_goldmine=advertiser.is_goldmine,
                is_watchlisted=advertiser.is_watchlisted,
                last_expanded_at=advertiser.last_expanded_at,
                **summary,
            )
        )
    links.sort(
        key=lambda item: (
            item.reported_ads is not None,
            item.reported_ads or 0,
            item.last_seen_at or datetime.min.replace(tzinfo=UTC),
            item.advertiser_name.lower(),
        ),
        reverse=True,
    )
    return ProjectAdvertisersResponse(
        project_id=project.id,
        domain=project.domain,
        brand_name=project.brand_name,
        collection_state="AVAILABLE" if observations else "NOT_COLLECTED",
        advertisers=links,
    )


@router.get("/advertisers/{advertiser_id}/projects", response_model=AdvertiserProjectsResponse)
def advertiser_projects(
    advertiser_id: int, db: Session = Depends(get_db)
) -> AdvertiserProjectsResponse:
    advertiser = db.get(Advertiser, advertiser_id)
    if advertiser is None:
        raise HTTPException(status_code=404, detail="advertiser not found")
    observations = list(
        db.scalars(select(AdObservation).where(AdObservation.advertiser_id == advertiser_id))
    )
    grouped: dict[int, list[AdObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.project_id].append(observation)
    projects = {
        project.id: project
        for project in db.scalars(select(Project).where(Project.id.in_(list(grouped))))
    } if grouped else {}
    links: list[AdvertiserProjectLink] = []
    for related_project_id, items in grouped.items():
        project = projects.get(related_project_id)
        if project is None:
            continue
        links.append(
            AdvertiserProjectLink(
                project_id=project.id,
                domain=project.domain,
                brand_name=project.brand_name,
                category=project.category,
                **_relationship_summary(items),
            )
        )
    links.sort(
        key=lambda item: (
            item.last_seen_at or datetime.min.replace(tzinfo=UTC),
            item.brand_name.lower(),
        ),
        reverse=True,
    )
    return AdvertiserProjectsResponse(
        advertiser_id=advertiser.id,
        advertiser_name=advertiser.verified_name,
        advertiser_location=advertiser.verified_location,
        classification=advertiser.classification,
        confidence=advertiser.confidence,
        source_url=advertiser.source_url,
        collection_state="AVAILABLE" if observations else "NOT_COLLECTED",
        projects=links,
    )


@router.get("/projects/{project_id}/network", response_model=ProjectNetworkResponse)
def project_network(
    project_id: int, db: Session = Depends(get_db)
) -> ProjectNetworkResponse:
    center = project_advertisers(project_id, db)
    expanded: list[ProjectNetworkAdvertiser] = []
    for link in center.advertisers:
        related = advertiser_projects(link.advertiser_id, db)
        expanded.append(
            ProjectNetworkAdvertiser(
                **link.model_dump(),
                projects=related.projects,
            )
        )
    return ProjectNetworkResponse(
        project_id=center.project_id,
        domain=center.domain,
        brand_name=center.brand_name,
        collection_state=center.collection_state,
        advertisers=expanded,
    )


@router.post("/captures", response_model=RawCaptureRead)
def create_capture(
    payload: RawCaptureCreate,
    request: Request,
    idempotency_key_header: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    db: Session = Depends(get_db),
) -> RawCapture:
    captured_at = _capture_now()
    effective_snapshot_date = payload.snapshot_date or captured_at.date()
    canonical_payload = payload.model_copy(update={"snapshot_date": effective_snapshot_date})
    idempotency_key = _normalize_idempotency_key(request, idempotency_key_header)
    capture_identity = _capture_identity(payload, idempotency_key)
    primary_hash, correction_hash = _capture_hashes(canonical_payload, capture_identity)

    parsed_payload = canonical_payload.model_dump(mode="json", exclude_none=True)
    parsed_payload["capture_identity"] = capture_identity
    has_structured = bool(canonical_payload.advertiser_name and canonical_payload.project_domain)
    capture_hash = primary_hash
    capture: RawCapture | None = None
    for _attempt in range(3):
        existing = db.scalar(select(RawCapture).where(RawCapture.capture_hash == capture_hash))
        if existing is not None:
            resolved = _resolve_existing_capture(
                existing,
                capture_identity,
                canonical_payload,
            )
            if resolved is not None:
                return resolved
            if correction_hash is not None and capture_hash == primary_hash:
                capture_hash = correction_hash
                continue
            if capture_identity["mode"] == "IDEMPOTENCY_KEY":
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for different capture content",
                )
            raise HTTPException(status_code=409, detail="capture identity collision")

        candidate = RawCapture(
            source_url=canonical_payload.source_url,
            page_title=canonical_payload.page_title,
            selected_text=canonical_payload.selected_text,
            visible_text=canonical_payload.visible_text,
            captured_at=captured_at,
            status=CaptureStatus.PARSED if has_structured else CaptureStatus.NEEDS_REVIEW,
            parsed_payload=parsed_payload,
            capture_hash=capture_hash,
        )
        db.add(candidate)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        capture = candidate
        break
    if capture is None:
        raise HTTPException(
            status_code=409,
            detail="capture identity is being created concurrently",
        )

    materialization: dict[str, int | bool] | None = None
    if has_structured:
        observation, created = _materialize_capture(db, capture, canonical_payload)
        materialization = {"observation_id": observation.id, "created": created}
        capture.parsed_payload = {**parsed_payload, "materialization": materialization}

    audit_payload: dict[str, object] = {
        "source_url": canonical_payload.source_url,
        "structured": has_structured,
        "capture_identity": capture_identity,
    }
    if materialization is not None:
        audit_payload["materialization"] = materialization
    _audit(
        db,
        "RawCapture",
        str(capture.id),
        AuditAction.IMPORT,
        audit_payload,
    )
    db.commit()
    db.refresh(capture)
    return capture


@router.get("/captures", response_model=list[RawCaptureRead])
def list_captures(
    limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)
) -> list[RawCapture]:
    return list(db.scalars(select(RawCapture).order_by(RawCapture.captured_at.desc()).limit(limit)))


@router.get("/captures/review-queue", response_model=list[RawCaptureReviewItem])
def capture_review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[RawCapture]:
    return list(
        db.scalars(
            select(RawCapture)
            .where(RawCapture.status.in_({CaptureStatus.RAW, CaptureStatus.NEEDS_REVIEW}))
            .where(
                ~select(AdObservation.id)
                .where(AdObservation.raw_capture_id == RawCapture.id)
                .exists()
            )
            .order_by(RawCapture.captured_at.asc(), RawCapture.id.asc())
            .limit(limit)
        )
    )


@router.post("/captures/{capture_id}/review", response_model=RawCaptureRead)
def review_capture(
    capture_id: int,
    payload: RawCaptureReviewRequest,
    db: Session = Depends(get_db),
) -> RawCapture:
    capture = db.get(RawCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="capture not found")

    if payload.action == "REJECT":
        if capture.status == CaptureStatus.PARSED:
            raise HTTPException(status_code=409, detail="parsed capture cannot be rejected")
        reason = (payload.reason or "").strip()
        if not reason:
            raise HTTPException(status_code=422, detail="reason is required to reject a capture")
        if _rejected_capture_is_idempotent(capture, reason):
            return capture
        if not _claim_capture_review(db, capture.id, CaptureStatus.REJECTED):
            capture = _reload_capture_after_failed_claim(db, capture.id)
            if capture.status == CaptureStatus.PARSED:
                raise HTTPException(status_code=409, detail="parsed capture cannot be rejected")
            if _rejected_capture_is_idempotent(capture, reason):
                return capture
            raise HTTPException(status_code=409, detail="capture review decision changed")
        capture.status = CaptureStatus.REJECTED
        capture.parser_version = "review-v1"
        capture.parsed_payload = {
            **(capture.parsed_payload or {}),
            "review": {
                "action": "REJECT",
                "reviewed_by": payload.reviewed_by,
                "reason": reason,
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
        }
        _audit(
            db,
            "RawCapture",
            str(capture.id),
            AuditAction.UPDATE,
            {"review_action": "REJECT", "reviewed_by": payload.reviewed_by, "reason": reason},
            actor=payload.reviewed_by,
        )
        db.commit()
        db.refresh(capture)
        return capture

    if capture.status == CaptureStatus.REJECTED:
        raise HTTPException(status_code=409, detail="rejected capture cannot be accepted")
    if _accepted_capture_is_idempotent(capture, payload):
        return capture

    existing_payload = dict(capture.parsed_payload or {})
    stored_capture_identity = existing_payload.get("capture_identity")
    review_fields = payload.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    review_fields.pop("action", None)
    review_fields.pop("reason", None)
    reviewed_by = review_fields.pop("reviewed_by", payload.reviewed_by)
    supplied_metadata = review_fields.pop("metadata", None)
    existing_metadata = existing_payload.get("metadata")
    if not isinstance(existing_metadata, dict):
        existing_metadata = {}
    if supplied_metadata is not None:
        review_fields["metadata"] = {**existing_metadata, **supplied_metadata}
    merged_payload = {
        **existing_payload,
        **review_fields,
        "source_url": capture.source_url,
        "page_title": capture.page_title,
        "selected_text": capture.selected_text,
        "visible_text": capture.visible_text,
    }
    structured = RawCaptureCreate.model_validate(merged_payload)
    if structured.snapshot_date is None:
        captured_at = _utc(capture.captured_at) or datetime.now(UTC)
        structured = structured.model_copy(update={"snapshot_date": captured_at.date()})
    if not _claim_capture_review(db, capture.id, CaptureStatus.PARSED):
        capture = _reload_capture_after_failed_claim(db, capture.id)
        if capture.status == CaptureStatus.REJECTED:
            raise HTTPException(status_code=409, detail="rejected capture cannot be accepted")
        if _accepted_capture_is_idempotent(capture, payload):
            return capture
        raise HTTPException(status_code=409, detail="capture review decision changed")
    observation, created = _materialize_capture(db, capture, structured)
    materialization = {"observation_id": observation.id, "created": created}
    capture.status = CaptureStatus.PARSED
    capture.parser_version = "review-v1"
    capture.parsed_payload = {
        **structured.model_dump(mode="json", exclude_none=True),
        "review": {
            "action": "ACCEPT",
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(UTC).isoformat(),
        },
        "materialization": materialization,
    }
    if isinstance(stored_capture_identity, dict):
        capture.parsed_payload = {
            **capture.parsed_payload,
            "capture_identity": stored_capture_identity,
        }
    _audit(
        db,
        "RawCapture",
        str(capture.id),
        AuditAction.UPDATE,
        {
            "review_action": "ACCEPT",
            "reviewed_by": reviewed_by,
            "materialization": materialization,
        },
        actor=reviewed_by,
    )
    db.commit()
    db.refresh(capture)
    return capture


@router.get("/radar", response_model=list[ProjectRadarItem])
def radar(db: Session = Depends(get_db)) -> list[ProjectRadarItem]:
    projects = list(db.scalars(select(Project).order_by(Project.brand_name)))
    observations = list(db.scalars(select(AdObservation)))
    by_project: dict[int, list[AdObservation]] = defaultdict(list)
    for obs in observations:
        by_project[obs.project_id].append(obs)

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    output: list[ProjectRadarItem] = []

    for project in projects:
        items = by_project.get(project.id, [])
        if not items:
            output.append(
                ProjectRadarItem(
                    project_id=project.id,
                    domain=project.domain,
                    brand_name=project.brand_name,
                    category=project.category,
                    distinct_advertisers=None,
                    active_advertisers_30d=None,
                    top_advertiser_share=None,
                    new_advertisers_30d=None,
                    independent_advertiser_score=None,
                    score_label="DATA_MISSING",
                    first_seen_at=project.first_seen_at,
                    last_seen_at=project.last_seen_at,
                )
            )
            continue
        counts: Counter[int] = Counter()
        for item in items:
            metadata = item.metadata_json or {}
            weight = (
                max(int(metadata.get("reported_ad_count") or 0), 1)
                if metadata.get("evidence_type") == "ADVERTISER_RESULT_SET"
                else 1
            )
            counts[item.advertiser_id] += weight
        distinct = len(counts)
        total = sum(counts.values())
        top_share = max(counts.values(), default=0) / total if total else 1.0
        active_ids: set[int] = set()
        new_ids: set[int] = set()
        activity_complete = all(item.last_seen_at is not None for item in items)
        first_seen_complete = all(item.first_seen_at is not None for item in items)
        for item in items:
            last_seen = _utc(item.last_seen_at)
            first_seen = _utc(item.first_seen_at)
            if last_seen is not None and last_seen >= cutoff:
                active_ids.add(item.advertiser_id)
            if first_seen is not None and first_seen >= cutoff:
                new_ids.add(item.advertiser_id)

        scored = (
            independent_advertiser_score(
                AdvertiserScoreInput(
                    distinct_advertisers=distinct,
                    active_advertisers_30d=len(active_ids),
                    top_advertiser_share=top_share,
                    new_advertisers_30d=len(new_ids),
                )
            )
            if activity_complete and first_seen_complete
            else None
        )
        output.append(
            ProjectRadarItem(
                project_id=project.id,
                domain=project.domain,
                brand_name=project.brand_name,
                category=project.category,
                distinct_advertisers=distinct,
                active_advertisers_30d=(len(active_ids) if activity_complete else None),
                top_advertiser_share=round(top_share, 4),
                new_advertisers_30d=(len(new_ids) if first_seen_complete else None),
                independent_advertiser_score=(scored.score if scored else None),
                score_label=(scored.label if scored else "PARTIAL_ACTIVITY_DATA"),
                first_seen_at=project.first_seen_at,
                last_seen_at=project.last_seen_at,
            )
        )

    return sorted(
        output,
        key=lambda item: (
            item.independent_advertiser_score
            if item.independent_advertiser_score is not None
            else -1,
            item.distinct_advertisers if item.distinct_advertisers is not None else -1,
        ),
        reverse=True,
    )


@router.get("/graph", response_model=GraphResponse)
def graph(db: Session = Depends(get_db)) -> GraphResponse:
    advertisers = list(db.scalars(select(Advertiser)))
    projects = list(db.scalars(select(Project)))
    observations = list(db.scalars(select(AdObservation)))

    nodes = [
        GraphNode(
            id=f"advertiser:{item.id}",
            type="ADVERTISER",
            label=item.verified_name,
            metadata={
                "location": item.verified_location,
                "classification": item.classification.value,
                "confidence": item.confidence,
            },
        )
        for item in advertisers
    ]
    nodes.extend(
        GraphNode(
            id=f"project:{item.id}",
            type="PROJECT",
            label=item.brand_name,
            metadata={"domain": item.domain, "category": item.category},
        )
        for item in projects
    )

    edge_counts = Counter((item.advertiser_id, item.project_id) for item in observations)
    edges = [
        GraphEdge(
            source=f"advertiser:{advertiser_id}",
            target=f"project:{project_id}",
            type="ADVERTISER_RUNS_PROJECT",
            weight=weight,
        )
        for (advertiser_id, project_id), weight in edge_counts.items()
    ]
    return GraphResponse(nodes=nodes, edges=edges)
