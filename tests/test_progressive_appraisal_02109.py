from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AppraisalJobStatus
from afi_os.main import app
from afi_os.models import AppraisalJob
from afi_os.services import appraisal_jobs

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _wait_job(job_id: int, timeout: float = 2) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/appraise/jobs/{job_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] in {"DONE", "FAILED"}:
            return body
        time.sleep(0.02)
    raise AssertionError("progressive appraisal job did not finish")


def test_fast_path_returns_job_and_independent_source_states(monkeypatch) -> None:
    monkeypatch.setattr(
        appraisal_jobs,
        "_collect_keyword",
        lambda db, job, project: {
            "status": "NO_DATA",
            "detail": "Google không có volume cho domain này",
            "source_urls": [],
        },
    )
    monkeypatch.setattr(
        appraisal_jobs,
        "_collect_traffic",
        lambda db, job, project: {
            "status": "CONNECTION_REQUIRED",
            "detail": "Chưa kết nối traffic",
            "source_urls": [],
        },
    )
    monkeypatch.setattr(
        appraisal_jobs,
        "_collect_terms",
        lambda db, job, project: {
            "status": "MANUAL_INPUT_REQUIRED",
            "detail": "Site chặn crawler",
            "source_urls": [f"https://{project.domain}/"],
        },
    )
    monkeypatch.setitem(appraisal_jobs.COLLECTORS, "keyword", appraisal_jobs._collect_keyword)
    monkeypatch.setitem(appraisal_jobs.COLLECTORS, "traffic", appraisal_jobs._collect_traffic)
    monkeypatch.setitem(appraisal_jobs.COLLECTORS, "terms", appraisal_jobs._collect_terms)

    started = time.monotonic()
    response = client.post("/api/appraise", json={"domain": "progressive.example"})
    elapsed = time.monotonic() - started

    assert response.status_code == 200, response.text
    body = response.json()
    assert elapsed < 2
    assert body["job_id"]
    final = _wait_job(body["job_id"])
    fields = final["appraisal"]["field_statuses"]
    assert fields["keyword"]["label"] == "Không tìm thấy dữ liệu"
    assert fields["traffic"]["label"] == "Chưa nối nguồn dữ liệu"
    assert fields["terms"]["color"] == "yellow"
    assert "cần đọc tay" in fields["terms"]["label"]
    assert fields["advertisers"]["detail"] == "Tính năng sẽ có khi nối minhbach/SerpApi."
    assert fields["niche"]["label"] == "Chưa nối nguồn dữ liệu"


def test_retry_one_source_does_not_reset_other_sources(monkeypatch) -> None:
    for source_name in appraisal_jobs.EXECUTABLE_SOURCES:
        monkeypatch.setitem(
            appraisal_jobs.COLLECTORS,
            source_name,
            lambda db, job, project: {
                "status": "NO_DATA",
                "detail": "Không có dữ liệu thử nghiệm",
                "source_urls": [],
            },
        )
    with SessionLocal() as db:
        response = appraisal_jobs.create_appraisal_job(
            db, "retry-one.example", wait_for_keyword=False
        )
        job_id = response.job_id
    assert job_id is not None
    _wait_job(job_id, timeout=5)
    with SessionLocal() as db:
        before = dict(db.get(AppraisalJob, job_id).per_source_json)

    monkeypatch.setitem(
        appraisal_jobs.COLLECTORS,
        "traffic",
        lambda db, job, project: {
            "status": "NO_DATA",
            "detail": "Không có traffic",
            "source_urls": [],
        },
    )
    response = client.post(f"/api/appraise/jobs/{job_id}/retry/traffic", json={})
    assert response.status_code == 200, response.text
    final = _wait_job(job_id, timeout=2)
    after = final["appraisal"]["field_statuses"]
    assert after["traffic"]["label"] == "Không tìm thấy dữ liệu"
    assert after["keyword"]["label"] == before["keyword"]["label"]
    assert after["keyword"]["detail"] == before["keyword"]["detail"]
    assert after["terms"]["label"] == before["terms"]["label"]
    assert after["terms"]["detail"] == before["terms"]["detail"]


def test_stale_running_job_becomes_failed_and_keeps_retryable_state() -> None:
    with SessionLocal() as db:
        project = appraisal_jobs.ensure_appraisal_project(db, "stale-progress.example")
        old = datetime.now(UTC) - timedelta(minutes=11)
        job = AppraisalJob(
            project_id=project.id,
            domain=project.domain,
            status=AppraisalJobStatus.RUNNING,
            per_source_json={
                "keyword": appraisal_jobs._source("loading", "Đang lấy từ khoá…"),
                "traffic": appraisal_jobs._source("ready", "Đã có dữ liệu", color="green"),
                "terms": appraisal_jobs._source("loading", "Đang đọc điều khoản…"),
                "advertisers": appraisal_jobs._source(
                    "pending_source", "Chưa nối nguồn dữ liệu"
                ),
            },
            started_at=old,
        )
        db.add(job)
        db.commit()
        job_id = job.id
        changed = appraisal_jobs.recover_stale_appraisal_jobs(db)
        db.refresh(job)
        assert changed == 1
        assert job.status == AppraisalJobStatus.FAILED
        assert job.per_source_json["keyword"]["retryable"] is True
        assert job.per_source_json["traffic"]["status"] == "ready"

    response = client.get(f"/api/appraise/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"


def test_ui_polls_each_second_and_exposes_four_truthful_empty_states() -> None:
    script = open("apps/web/app.js", encoding="utf-8").read()
    assert "window.setTimeout(poll, 1000)" in script
    assert "Chưa nối nguồn dữ liệu" in script
    assert "Không tìm thấy dữ liệu" in script
    assert "cần đọc tay" in script
    assert "Lỗi:" in script
    assert "data-appraisal-retry" in script
    assert "data-appraisal-refresh" in script
    assert "Chưa có số liệu" in script


def test_connected_source_without_access_is_a_technical_error() -> None:
    state = appraisal_jobs._result_source(
        {
            "status": "ACCESS_REQUIRED",
            "detail": "Google Ads cần Basic Access cho Keyword Planner.",
            "source_urls": ["https://developers.google.com/google-ads/api"],
        },
        duration_ms=25,
    )

    assert state["status"] == "error"
    assert state["color"] == "red"
    assert state["label"].startswith("Lỗi:")
    assert state["retryable"] is True


def test_no_google_ads_write_operations_exist_in_progressive_workers() -> None:
    source = open("src/afi_os/services/appraisal_jobs.py", encoding="utf-8").read()
    assert "generateKeywordIdeas" not in source
    assert "mutate" not in source.lower()
    assert "createCampaign" not in source
