from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import CaptureStatus
from afi_os.main import app
from afi_os.models import AdObservation, Advertiser, AuditLog, Project, RawCapture

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)


def _read_only_counts() -> tuple[int, int, int, int]:
    with SessionLocal() as db:
        return (
            int(db.scalar(select(func.count()).select_from(Advertiser)) or 0),
            int(db.scalar(select(func.count()).select_from(Project)) or 0),
            int(db.scalar(select(func.count()).select_from(AdObservation)) or 0),
            int(db.scalar(select(func.count()).select_from(AuditLog)) or 0),
        )


def test_operations_capture_target_matches_oldest_review_queue_without_writes() -> None:
    oldest_time = datetime(1970, 1, 1, tzinfo=UTC)
    captures = [
        RawCapture(
            source_url="https://adstransparency.google.com/focus-oldest-0284",
            selected_text="Oldest focus target",
            captured_at=oldest_time,
            status=CaptureStatus.NEEDS_REVIEW,
            parsed_payload={},
            capture_hash=hashlib.sha256(b"focus-oldest-0284").hexdigest(),
        ),
        RawCapture(
            source_url="https://adstransparency.google.com/focus-next-0284",
            selected_text="Next focus target",
            captured_at=oldest_time + timedelta(seconds=1),
            status=CaptureStatus.RAW,
            parsed_payload={},
            capture_hash=hashlib.sha256(b"focus-next-0284").hexdigest(),
        ),
    ]
    with SessionLocal() as db:
        db.add_all(captures)
        db.commit()
        capture_ids = [capture.id for capture in captures]

    try:
        before = _read_only_counts()
        inbox = client.get("/api/operations/inbox")
        queue = client.get("/api/ad-intelligence/captures/review-queue?limit=50")
        assert inbox.status_code == 200, inbox.text
        assert queue.status_code == 200, queue.text

        review_items = [
            item
            for item in inbox.json()["items"]
            if item["item_type"] == "AD_CAPTURE_REVIEW"
        ]
        assert len(review_items) == 1
        assert review_items[0]["action_view"] == "intelligence"
        assert review_items[0]["entity_id"] == str(capture_ids[0])
        assert queue.json()[0]["id"] == capture_ids[0]
        assert _read_only_counts() == before
    finally:
        with SessionLocal() as db:
            for capture_id in capture_ids:
                capture = db.get(RawCapture, capture_id)
                if capture is not None:
                    db.delete(capture)
            db.commit()


def test_operations_capture_focus_ui_contract_and_stale_fallback() -> None:
    page = Path("apps/web/index.html").read_text(encoding="utf-8")
    script = Path("apps/web/app.js").read_text(encoding="utf-8")
    styles = Path("apps/web/styles.css").read_text(encoding="utf-8")

    assert 'data-operation-item-type="${esc(item.item_type)}"' in script
    assert 'data-operation-entity-id="${esc(item.entity_id || "")}"' in script
    assert (
        'id="captureReviewPanel" tabindex="-1" aria-labelledby="captureReviewTitle"'
        in page
    )
    assert 'id="captureReviewMessage"' in page
    assert ".review-row-target td" in styles

    open_start = script.index("async function openOperation(button)")
    open_end = script.index("async function loadRadar()", open_start)
    open_function = script[open_start:open_end]
    assert 'itemType === "AD_CAPTURE_REVIEW"' in open_function
    assert "switchView(view, {loadData: !isCaptureReviewOperation})" in open_function
    assert "await Promise.all([loadCaptureReviewQueue(), loadCaptures()])" in open_function
    assert open_function.index("await Promise.all") < open_function.index(
        "focusCaptureReviewTarget(entityId)"
    )
    assert 'method: "POST"' not in open_function

    focus_start = script.index("function focusCaptureReviewTarget(captureId)")
    focus_end = script.index("async function openOperation(button)", focus_start)
    focus_function = script[focus_start:focus_end]
    assert "row.dataset.captureReviewId === String(captureId)" in focus_function
    assert 'scrollIntoView({behavior: "auto", block: "center"})' in focus_function
    assert "firstBlankInput" in focus_function
    assert "focusTarget.focus({preventScroll: true})" in focus_function
    assert 'return "FALLBACK"' in focus_function
    assert 'return "EMPTY"' in focus_function
    assert "không còn chờ duyệt" in focus_function
    assert "hàng đợi hiện trống" in focus_function
    assert 'if (focusResult !== "EXACT") await loadOperations()' in open_function
