from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from afi_os.api import ad_intelligence
from afi_os.db import Base, SessionLocal, engine
from afi_os.main import app
from afi_os.models import RawCapture
from afi_os.schemas import RawCaptureCreate

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _payload(unique: str = "base") -> dict:
    return {
        "source_url": f"https://adstransparency.google.com/identity-v2-{unique}",
        "page_title": "Identity v2",
        "selected_text": "Visible ad evidence",
        "visible_text": "Full visible page evidence",
        "advertiser_name": "Identity Advertiser",
        "advertiser_location": "US",
        "project_domain": "identity-project.example",
        "brand_name": "Identity Project",
        "category": "Software",
        "ad_format": "TEXT",
        "headline": "Original headline",
        "description": "Original description",
        "display_url": "identity-project.example/demo",
        "landing_domain": "publisher.example",
        "country": "us",
        "language": "en",
        "first_seen_at": "2026-08-10T02:30:00Z",
        "last_seen_at": "2026-08-10T03:30:00Z",
        "snapshot_date": "2026-08-10",
        "metadata": {
            "capture_method": "identity-v2-test",
            "nested": {"beta": 2, "alpha": 1},
        },
    }


def _capture_count() -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.count()).select_from(RawCapture)) or 0)


def _legacy_hash(payload: dict) -> str:
    normalized = RawCaptureCreate.model_validate(payload)
    joined = "\n".join(
        part or ""
        for part in (
            normalized.source_url,
            normalized.selected_text,
            normalized.visible_text,
            normalized.advertiser_name,
            normalized.project_domain,
            normalized.headline,
            normalized.description,
            str(normalized.snapshot_date),
        )
    )
    return hashlib.sha256(joined.encode()).hexdigest()


def test_no_key_exact_retry_is_idempotent_and_identity_is_private() -> None:
    payload = _payload("exact-retry")
    first = client.post("/api/ad-intelligence/captures", json=payload)
    second = client.post("/api/ad-intelligence/captures", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    identity = first.json()["parsed_payload"]["capture_identity"]
    assert identity == {
        "version": "capture-v2",
        "mode": "CONTENT",
        "namespace": "afi-os-local:capture-intake",
        "fingerprint": identity["fingerprint"],
    }
    assert len(identity["fingerprint"]) == 64
    with SessionLocal() as db:
        stored = db.get(RawCapture, first.json()["id"])
        assert stored is not None
        assert stored.capture_hash == _legacy_hash(payload)
        assert stored.parser_version == "manual-v1"
    assert _capture_count() == 1


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("page_title", "Corrected page title"),
        ("selected_text", "Corrected selected evidence"),
        ("visible_text", "Corrected full evidence"),
        ("headline", "Corrected headline"),
        ("description", "Corrected description"),
        ("advertiser_name", "Corrected Advertiser"),
        ("project_domain", "corrected-project.example"),
        ("landing_domain", "corrected-publisher.example"),
        ("country", "VN"),
        ("metadata", {"capture_method": "corrected", "nested": {"alpha": 1}}),
    ],
)
def test_no_key_same_day_semantic_correction_creates_a_new_capture(
    field: str,
    changed: object,
) -> None:
    payload = _payload(f"same-day-{field}")
    first = client.post("/api/ad-intelligence/captures", json=payload)
    corrected = deepcopy(payload)
    corrected[field] = changed
    second = client.post("/api/ad-intelligence/captures", json=corrected)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] != first.json()["id"]
    assert (
        second.json()["parsed_payload"]["capture_identity"]["fingerprint"]
        != first.json()["parsed_payload"]["capture_identity"]["fingerprint"]
    )


def test_no_key_canonical_equivalence_is_idempotent() -> None:
    first_payload = _payload("canonical")
    first_payload["project_domain"] = "https://WWW.IDENTITY-PROJECT.EXAMPLE/path"
    first_payload["landing_domain"] = "HTTP://Publisher.Example/landing"
    first_payload["country"] = "us"
    first_payload["first_seen_at"] = "2026-08-10T02:30:00+00:00"
    second_payload = deepcopy(first_payload)
    second_payload["project_domain"] = "identity-project.example"
    second_payload["landing_domain"] = "publisher.example"
    second_payload["country"] = "US"
    second_payload["first_seen_at"] = "2026-08-10T05:30:00+03:00"
    second_payload["metadata"] = {
        "nested": {"alpha": 1, "beta": 2},
        "capture_method": "identity-v2-test",
    }

    first = client.post("/api/ad-intelligence/captures", json=first_payload)
    second = client.post("/api/ad-intelligence/captures", json=second_payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


def test_no_key_same_content_on_different_day_creates_a_new_capture() -> None:
    payload = _payload("new-day")
    first = client.post("/api/ad-intelligence/captures", json=payload)
    next_day = {**payload, "snapshot_date": "2026-08-11"}
    second = client.post("/api/ad-intelligence/captures", json=next_day)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] != first.json()["id"]


def test_keyed_retry_with_omitted_date_survives_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload("key-midnight")
    payload.pop("snapshot_date")
    headers = {"Idempotency-Key": "midnight-retry-0285"}
    monkeypatch.setattr(
        ad_intelligence,
        "_capture_now",
        lambda: datetime(2026, 8, 10, 23, 59, tzinfo=UTC),
    )
    first = client.post("/api/ad-intelligence/captures", json=payload, headers=headers)
    monkeypatch.setattr(
        ad_intelligence,
        "_capture_now",
        lambda: datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
    )
    retry = client.post("/api/ad-intelligence/captures", json=payload, headers=headers)

    assert first.status_code == 200, first.text
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == first.json()["id"]
    assert first.json()["parsed_payload"]["snapshot_date"] == "2026-08-10"
    assert (
        first.json()["parsed_payload"]["capture_identity"]["fingerprint"]
        == retry.json()["parsed_payload"]["capture_identity"]["fingerprint"]
    )


def test_no_key_omitted_date_keeps_legacy_daily_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload("content-midnight")
    payload.pop("snapshot_date")
    monkeypatch.setattr(
        ad_intelligence,
        "_capture_now",
        lambda: datetime(2026, 8, 10, 23, 59, tzinfo=UTC),
    )
    first = client.post("/api/ad-intelligence/captures", json=payload)
    monkeypatch.setattr(
        ad_intelligence,
        "_capture_now",
        lambda: datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
    )
    next_day = client.post("/api/ad-intelligence/captures", json=payload)

    assert first.status_code == 200, first.text
    assert next_day.status_code == 200, next_day.text
    assert next_day.json()["id"] != first.json()["id"]
    assert first.json()["parsed_payload"]["snapshot_date"] == "2026-08-10"
    assert next_day.json()["parsed_payload"]["snapshot_date"] == "2026-08-11"


def test_idempotency_key_exact_retry_returns_same_capture_and_stores_only_hash() -> None:
    payload = _payload("keyed")
    key = "extension-click-0285-secret-value"
    headers = {"Idempotency-Key": key}
    first = client.post("/api/ad-intelligence/captures", json=payload, headers=headers)
    second = client.post("/api/ad-intelligence/captures", json=payload, headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    identity = first.json()["parsed_payload"]["capture_identity"]
    assert identity["mode"] == "IDEMPOTENCY_KEY"
    assert len(identity["key_hash"]) == 64
    assert key not in first.text
    with SessionLocal() as db:
        stored = db.get(RawCapture, first.json()["id"])
        assert stored is not None
        assert key not in stored.capture_hash
        assert key not in str(stored.parsed_payload)


def test_idempotency_key_reuse_with_changed_content_or_day_is_conflict() -> None:
    payload = _payload("key-conflict")
    headers = {"idempotency-key": "one-logical-capture-0285"}
    first = client.post("/api/ad-intelligence/captures", json=payload, headers=headers)
    changed = deepcopy(payload)
    changed["headline"] = "Correction must not be swallowed"
    conflict = client.post("/api/ad-intelligence/captures", json=changed, headers=headers)
    changed_day = client.post(
        "/api/ad-intelligence/captures",
        json={**payload, "snapshot_date": "2026-08-11"},
        headers=headers,
    )

    assert first.status_code == 200, first.text
    assert conflict.status_code == 409, conflict.text
    assert "different capture content" in conflict.json()["detail"]
    assert changed_day.status_code == 409, changed_day.text
    assert _capture_count() == 1


@pytest.mark.parametrize(
    "key",
    ["", "   ", "contains space", "contains,comma", "x" * 201],
)
def test_invalid_idempotency_key_is_rejected_without_writes(key: str) -> None:
    response = client.post(
        "/api/ad-intelligence/captures",
        json=_payload(f"invalid-key-{len(key)}"),
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 422, response.text
    assert _capture_count() == 0


def test_duplicate_idempotency_headers_are_rejected_without_writes() -> None:
    response = client.post(
        "/api/ad-intelligence/captures",
        json=_payload("duplicate-key-header"),
        headers=[("Idempotency-Key", "first"), ("Idempotency-Key", "second")],
    )
    assert response.status_code == 422, response.text
    assert _capture_count() == 0


def test_non_finite_metadata_is_rejected_without_writes() -> None:
    response = client.post(
        "/api/ad-intelligence/captures",
        content=(
            '{"source_url":"https://adstransparency.google.com/non-finite-0285",'
            '"metadata":{"score":NaN}}'
        ),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert _capture_count() == 0


def test_capture_identity_is_preserved_through_accept_and_reject() -> None:
    accept_created = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/identity-accept-0285",
            "selected_text": "Needs identity review",
            "snapshot_date": "2026-08-10",
        },
        headers={"Idempotency-Key": "accept-identity-0285"},
    )
    original_identity = accept_created.json()["parsed_payload"]["capture_identity"]
    accepted = client.post(
        f"/api/ad-intelligence/captures/{accept_created.json()['id']}/review",
        json={
            "action": "ACCEPT",
            "reviewed_by": "Identity Reviewer",
            "advertiser_name": "Identity Review Advertiser",
            "project_domain": "identity-review.example",
            "metadata": {"capture_identity": {"fingerprint": "spoofed"}},
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["parsed_payload"]["capture_identity"] == original_identity

    reject_created = client.post(
        "/api/ad-intelligence/captures",
        json={
            "source_url": "https://adstransparency.google.com/identity-reject-0285",
            "visible_text": "Reject identity review",
            "snapshot_date": "2026-08-10",
        },
    )
    reject_identity = reject_created.json()["parsed_payload"]["capture_identity"]
    rejected = client.post(
        f"/api/ad-intelligence/captures/{reject_created.json()['id']}/review",
        json={
            "action": "REJECT",
            "reviewed_by": "Identity Reviewer",
            "reason": "Not relevant",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["parsed_payload"]["capture_identity"] == reject_identity


def test_existing_v1_row_remains_the_no_header_idempotent_result() -> None:
    payload = _payload("upgrade-boundary")
    normalized = RawCaptureCreate.model_validate(payload)
    with SessionLocal() as db:
        legacy = RawCapture(
            source_url=normalized.source_url,
            page_title=normalized.page_title,
            selected_text=normalized.selected_text,
            visible_text=normalized.visible_text,
            captured_at=datetime(2026, 8, 10, tzinfo=UTC),
            parsed_payload=normalized.model_dump(mode="json", exclude_none=True),
            capture_hash=_legacy_hash(payload),
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    created = client.post("/api/ad-intelligence/captures", json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["id"] == legacy_id
    assert "capture_identity" not in created.json()["parsed_payload"]
    assert _capture_count() == 1


def test_same_day_correction_is_not_swallowed_by_existing_v1_bucket() -> None:
    payload = _payload("legacy-correction")
    normalized = RawCaptureCreate.model_validate(payload)
    with SessionLocal() as db:
        legacy = RawCapture(
            source_url=normalized.source_url,
            page_title=normalized.page_title,
            selected_text=normalized.selected_text,
            visible_text=normalized.visible_text,
            captured_at=datetime(2026, 8, 10, tzinfo=UTC),
            parsed_payload=normalized.model_dump(mode="json", exclude_none=True),
            capture_hash=_legacy_hash(payload),
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    corrected = {**payload, "page_title": "Same-day corrected title"}
    created = client.post("/api/ad-intelligence/captures", json=corrected)
    retry = client.post("/api/ad-intelligence/captures", json=corrected)

    assert created.status_code == 200, created.text
    assert retry.status_code == 200, retry.text
    assert created.json()["id"] != legacy_id
    assert retry.json()["id"] == created.json()["id"]
    assert created.json()["parsed_payload"]["capture_identity"]["version"] == "capture-v2"
    assert _capture_count() == 2


def test_openapi_exposes_optional_idempotency_header() -> None:
    parameters = client.get("/openapi.json").json()["paths"][
        "/api/ad-intelligence/captures"
    ]["post"]["parameters"]
    header = next(parameter for parameter in parameters if parameter["name"] == "Idempotency-Key")
    assert header["in"] == "header"
    assert header["required"] is False
    assert all(parameter["name"] != "Idempotency-Namespace" for parameter in parameters)


def test_concurrent_exact_key_retry_returns_one_capture() -> None:
    payload = _payload("concurrent-exact-key")
    barrier = Barrier(2)

    def send() -> tuple[int, dict]:
        with TestClient(app, raise_server_exceptions=False) as concurrent_client:
            barrier.wait(timeout=5)
            response = concurrent_client.post(
                "/api/ad-intelligence/captures",
                json=payload,
                headers={"Idempotency-Key": "concurrent-exact-key-0285"},
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=10) for future in (pool.submit(send), pool.submit(send))]

    assert [status for status, _body in results] == [200, 200]
    assert len({body["id"] for _status, body in results}) == 1
    assert _capture_count() == 1


def test_concurrent_key_reuse_with_different_content_is_200_and_409() -> None:
    base = _payload("concurrent-conflict")
    corrected = {**base, "headline": "Concurrent correction"}
    barrier = Barrier(2)

    def send(payload: dict) -> tuple[int, dict]:
        with TestClient(app, raise_server_exceptions=False) as concurrent_client:
            barrier.wait(timeout=5)
            response = concurrent_client.post(
                "/api/ad-intelligence/captures",
                json=payload,
                headers={"Idempotency-Key": "concurrent-conflict-0285"},
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(send, base)
        second = pool.submit(send, corrected)
        results = [first.result(timeout=10), second.result(timeout=10)]

    assert sorted(status for status, _body in results) == [200, 409]
    assert _capture_count() == 1


def test_concurrent_no_key_exact_retry_returns_one_capture() -> None:
    payload = _payload("concurrent-content")
    barrier = Barrier(2)

    def send() -> tuple[int, dict]:
        with TestClient(app, raise_server_exceptions=False) as concurrent_client:
            barrier.wait(timeout=5)
            response = concurrent_client.post("/api/ad-intelligence/captures", json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=10) for future in (pool.submit(send), pool.submit(send))]

    assert [status for status, _body in results] == [200, 200]
    assert len({body["id"] for _status, body in results}) == 1
    assert _capture_count() == 1
