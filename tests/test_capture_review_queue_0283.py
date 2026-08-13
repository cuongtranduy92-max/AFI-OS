from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AuditAction, CaptureStatus
from afi_os.main import app
from afi_os.models import AdObservation, AuditLog, RawCapture

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)


def test_unstructured_capture_enters_review_queue_and_accepts_once() -> None:
    created = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/review-queue-0283",
            "page_title": "Unstructured ad evidence",
            "selected_text": "Review Queue advertiser promotes Review Queue AI",
            "headline": "Create faster",
            "metadata": {"capture_method": "review-queue-test"},
        },
    )
    assert created.status_code == 200, created.text
    capture_id = created.json()["id"]
    assert created.json()["status"] == "NEEDS_REVIEW"

    queue = client.get("/api/ad-intelligence/captures/review-queue")
    assert queue.status_code == 200, queue.text
    queued = next(item for item in queue.json() if item["id"] == capture_id)
    assert queued["selected_text"].startswith("Review Queue advertiser")

    inbox = client.get("/api/operations/inbox")
    assert inbox.status_code == 200, inbox.text
    assert any(item["item_type"] == "AD_CAPTURE_REVIEW" for item in inbox.json()["items"])

    review_payload = {
        "action": "ACCEPT",
        "reviewed_by": "Test Operator",
        "advertiser_name": "Review Queue Advertiser 0283",
        "advertiser_location": "US",
        "project_domain": "review-queue-0283.example",
        "brand_name": "Review Queue AI",
        "headline": "Create faster",
        "landing_domain": "publisher-0283.example",
        "country": "us",
    }
    accepted = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json=review_payload,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "PARSED"
    assert accepted.json()["parsed_payload"]["review"]["action"] == "ACCEPT"
    assert accepted.json()["parsed_payload"]["metadata"] == {
        "capture_method": "review-queue-test"
    }
    assert accepted.json()["parsed_payload"]["materialization"]["created"] is True

    repeated = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json=review_payload,
    )
    assert repeated.status_code == 200, repeated.text

    changed = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={**review_payload, "project_domain": "different-review-queue-0283.example"},
    )
    assert changed.status_code == 409, changed.text

    with SessionLocal() as db:
        observation_count = int(
            db.scalar(
                select(func.count())
                .select_from(AdObservation)
                .where(AdObservation.raw_capture_id == capture_id)
            )
            or 0
        )
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "RawCapture",
                AuditLog.entity_id == str(capture_id),
                AuditLog.action == AuditAction.UPDATE,
            )
            .order_by(AuditLog.id.desc())
        )
    assert observation_count == 1
    assert audit is not None
    assert audit.actor == "Test Operator"
    assert audit.payload_json["materialization"]["observation_id"] == accepted.json()[
        "parsed_payload"
    ]["materialization"]["observation_id"]

    queue_ids = {
        item["id"] for item in client.get("/api/ad-intelligence/captures/review-queue").json()
    }
    assert capture_id not in queue_ids

    radar = client.get("/api/ad-intelligence/radar")
    assert any(item["domain"] == "review-queue-0283.example" for item in radar.json())


def test_capture_rejection_requires_reason_and_cannot_be_reversed() -> None:
    created = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/review-reject-0283",
            "visible_text": "Unrelated page fragment",
        },
    )
    assert created.status_code == 200, created.text
    capture_id = created.json()["id"]

    missing_reason = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={"action": "REJECT", "reviewed_by": "Test Operator"},
    )
    assert missing_reason.status_code == 422, missing_reason.text

    rejected = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Test Operator",
            "reason": "Not an advertisement",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"

    repeated = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Test Operator",
            "reason": "Not an advertisement",
        },
    )
    assert repeated.status_code == 200, repeated.text

    changed_reason = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Test Operator",
            "reason": "A different irreversible reason",
        },
    )
    assert changed_reason.status_code == 409, changed_reason.text

    cannot_accept = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "ACCEPT",
            "advertiser_name": "Should Not Exist",
            "project_domain": "should-not-exist-0283.example",
        },
    )
    assert cannot_accept.status_code == 409, cannot_accept.text

    with SessionLocal() as db:
        stored = db.get(RawCapture, capture_id)
        assert stored is not None
        assert stored.status.value == "REJECTED"


def test_legacy_raw_capture_is_visible_and_reviewable() -> None:
    with SessionLocal() as db:
        capture = RawCapture(
            source_url="https://adstransparency.google.com/legacy-raw-0283",
            page_title="Legacy raw capture",
            selected_text="Legacy evidence waiting for review",
            status=CaptureStatus.RAW,
            parsed_payload={"headline": "Legacy headline"},
            capture_hash="legacy-raw-review-0283".ljust(64, "0"),
        )
        db.add(capture)
        db.commit()
        capture_id = capture.id

    queue = client.get("/api/ad-intelligence/captures/review-queue")
    assert queue.status_code == 200, queue.text
    assert capture_id in {item["id"] for item in queue.json()}

    inbox = client.get("/api/operations/inbox")
    assert inbox.status_code == 200, inbox.text
    review_item = next(
        item for item in inbox.json()["items"] if item["item_type"] == "AD_CAPTURE_REVIEW"
    )
    assert review_item["entity_id"] == str(capture_id)

    accepted = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "ACCEPT",
            "reviewed_by": "Test Operator",
            "advertiser_name": "Legacy Raw Advertiser 0283",
            "project_domain": "legacy-raw-0283.example",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "PARSED"

    with SessionLocal() as db:
        observation_count = int(
            db.scalar(
                select(func.count())
                .select_from(AdObservation)
                .where(AdObservation.raw_capture_id == capture_id)
            )
            or 0
        )
    assert observation_count == 1


def test_capture_validation_rejects_unsafe_identity_before_materialization() -> None:
    unsafe_url = client.post(
        "/api/ad-intelligence/captures",
        json={"source_url": "javascript:alert(1)", "visible_text": "unsafe"},
    )
    assert unsafe_url.status_code == 422, unsafe_url.text

    invalid_domain = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/invalid-domain-0283",
            "advertiser_name": "Invalid Domain Advertiser 0283",
            "project_domain": "not a domain",
        },
    )
    assert invalid_domain.status_code == 422, invalid_domain.text


def test_delayed_review_uses_capture_day_and_handles_existing_graph_dates() -> None:
    with SessionLocal() as db:
        capture = RawCapture(
            source_url="https://adstransparency.google.com/delayed-review-0283",
            selected_text="Delayed review evidence",
            captured_at=datetime(2026, 8, 1, 23, 45, tzinfo=UTC),
            status=CaptureStatus.RAW,
            parsed_payload={"headline": "Delayed headline"},
            capture_hash="delayed-review-0283".ljust(64, "0"),
        )
        db.add(capture)
        db.commit()
        capture_id = capture.id

    accepted = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "ACCEPT",
            "reviewed_by": "Date Reviewer",
            "advertiser_name": "Review Queue Advertiser 0283",
            "advertiser_location": "US",
            "project_domain": "review-queue-0283.example",
            "first_seen_at": "2026-08-01T22:00:00Z",
            "last_seen_at": "2026-08-02T01:00:00Z",
        },
    )
    assert accepted.status_code == 200, accepted.text
    materialization = accepted.json()["parsed_payload"]["materialization"]
    with SessionLocal() as db:
        observation = db.get(AdObservation, materialization["observation_id"])
        assert observation is not None
        assert observation.snapshot_date == date(2026, 8, 1)


def test_rejected_capture_can_be_recaptured_on_a_later_snapshot_day() -> None:
    common = {
        "source_url": "https://adstransparency.google.com/recapture-after-reject-0283",
        "visible_text": "Same ad evidence on another day",
    }
    first = client.post(
        "/api/ad-intelligence/captures",
        json={**common, "snapshot_date": "2026-08-03"},
    )
    assert first.status_code == 200, first.text
    rejected = client.post(
        f"/api/ad-intelligence/captures/{first.json()['id']}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Recapture Reviewer",
            "reason": "Insufficient identity on first day",
        },
    )
    assert rejected.status_code == 200, rejected.text

    second = client.post(
        "/api/ad-intelligence/captures",
        json={**common, "snapshot_date": "2026-08-04"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["status"] == "NEEDS_REVIEW"

    same_day_retry = client.post(
        "/api/ad-intelligence/captures",
        json={**common, "snapshot_date": "2026-08-04"},
    )
    assert same_day_retry.json()["id"] == second.json()["id"]

    cleanup = client.post(
        f"/api/ad-intelligence/captures/{second.json()['id']}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Recapture Reviewer",
            "reason": "Test cleanup",
        },
    )
    assert cleanup.status_code == 200, cleanup.text


def test_duplicate_ad_evidence_keeps_materialization_lineage() -> None:
    captures: list[int] = []
    for evidence in ("Evidence copy A", "Evidence copy B"):
        created = client.post(
            "/api/ad-intelligence/captures",
            json={
                "source_url": "https://adstransparency.google.com/lineage-0283",
                "visible_text": evidence,
                "headline": "Lineage ad 0283",
                "snapshot_date": "2026-08-05",
            },
        )
        assert created.status_code == 200, created.text
        captures.append(created.json()["id"])

    accepted_rows = []
    for capture_id in captures:
        accepted = client.post(
            f"/api/ad-intelligence/captures/{capture_id}/review",
            json={
                "action": "ACCEPT",
                "reviewed_by": "Lineage Reviewer",
                "advertiser_name": "Lineage Advertiser 0283",
                "project_domain": "lineage-project-0283.example",
            },
        )
        assert accepted.status_code == 200, accepted.text
        accepted_rows.append(accepted.json())

    first_link = accepted_rows[0]["parsed_payload"]["materialization"]
    second_link = accepted_rows[1]["parsed_payload"]["materialization"]
    assert first_link["created"] is True
    assert second_link == {"observation_id": first_link["observation_id"], "created": False}
    with SessionLocal() as db:
        observation = db.get(AdObservation, first_link["observation_id"])
        assert observation is not None
        assert observation.raw_capture_id == captures[0]
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "RawCapture",
                AuditLog.entity_id == str(captures[1]),
                AuditLog.action == AuditAction.UPDATE,
            )
            .order_by(AuditLog.id.desc())
        )
        assert audit is not None
        assert audit.payload_json["materialization"] == second_link


def test_materialized_legacy_raw_is_excluded_everywhere_and_cannot_be_reviewed() -> None:
    structured = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/materialized-raw-0283",
            "advertiser_name": "Materialized Raw Advertiser 0283",
            "project_domain": "materialized-raw-0283.example",
            "headline": "Already materialized",
        },
    )
    assert structured.status_code == 200, structured.text
    capture_id = structured.json()["id"]
    with SessionLocal() as db:
        capture = db.get(RawCapture, capture_id)
        assert capture is not None
        capture.status = CaptureStatus.RAW
        db.commit()

    queue = client.get("/api/ad-intelligence/captures/review-queue")
    assert capture_id not in {item["id"] for item in queue.json()}
    dashboard = client.get("/api/dashboard/summary")
    with SessionLocal() as db:
        expected = int(
            db.scalar(
                select(func.count())
                .select_from(RawCapture)
                .where(RawCapture.status.in_({CaptureStatus.RAW, CaptureStatus.NEEDS_REVIEW}))
                .where(
                    ~select(AdObservation.id)
                    .where(AdObservation.raw_capture_id == RawCapture.id)
                    .exists()
                )
            )
            or 0
        )
    assert dashboard.json()["captures_needing_review"] == expected

    rejected = client.post(
        f"/api/ad-intelligence/captures/{capture_id}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Legacy Guard Reviewer",
            "reason": "Must not overwrite materialized lineage",
        },
    )
    assert rejected.status_code == 409, rejected.text


def test_accept_reject_race_has_one_terminal_decision() -> None:
    created = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/review-race-0283",
            "visible_text": "Concurrent decision evidence",
        },
    )
    assert created.status_code == 200, created.text
    capture_id = created.json()["id"]
    barrier = Barrier(2)

    def decide(payload: dict[str, str]) -> tuple[int, dict]:
        with TestClient(app, raise_server_exceptions=False) as concurrent_client:
            barrier.wait(timeout=5)
            response = concurrent_client.post(
                f"/api/ad-intelligence/captures/{capture_id}/review", json=payload
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        accept_future = pool.submit(
            decide,
            {
                "action": "ACCEPT",
                "reviewed_by": "Accept Racer",
                "advertiser_name": "Race Advertiser 0283",
                "project_domain": "race-project-0283.example",
            },
        )
        reject_future = pool.submit(
            decide,
            {
                "action": "REJECT",
                "reviewed_by": "Reject Racer",
                "reason": "Opposing concurrent decision",
            },
        )
        results = [accept_future.result(timeout=10), reject_future.result(timeout=10)]

    assert sorted(status for status, _body in results) == [200, 409]
    with SessionLocal() as db:
        capture = db.get(RawCapture, capture_id)
        assert capture is not None
        observation_count = int(
            db.scalar(
                select(func.count())
                .select_from(AdObservation)
                .where(AdObservation.raw_capture_id == capture_id)
            )
            or 0
        )
        assert observation_count == (1 if capture.status == CaptureStatus.PARSED else 0)
