from __future__ import annotations

from types import SimpleNamespace
from urllib.error import URLError

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import AppraisalJobStatus, ResearchStatus
from afi_os.models import AppraisalJob
from afi_os.services import appraisal_jobs


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _job(db, domain: str) -> tuple[AppraisalJob, object]:  # type: ignore[no-untyped-def]
    project = appraisal_jobs.ensure_appraisal_project(db, domain)
    job = AppraisalJob(
        project_id=project.id,
        domain=domain,
        status=AppraisalJobStatus.RUNNING,
        per_source_json={},
    )
    db.add(job)
    db.commit()
    return job, project


def test_terms_empty_pages_are_not_retried(monkeypatch) -> None:
    calls = 0

    def collect(db, domain):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return {
            "run": SimpleNamespace(status=ResearchStatus.MANUAL_INPUT_REQUIRED),
            "program": None,
            "pages": [],
            "source_urls": [],
        }

    monkeypatch.setattr(appraisal_jobs, "collect_domain_proposal", collect)
    with SessionLocal() as db:
        job, project = _job(db, "empty-no-retry.example")
        result = appraisal_jobs._collect_terms(db, job, project)

    assert calls == 1
    assert result["status"] == "MANUAL_INPUT_REQUIRED"


def test_terms_network_exception_gets_one_retry(monkeypatch) -> None:
    calls = 0

    def collect(db, domain):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary")
        return {
            "run": SimpleNamespace(status=ResearchStatus.MANUAL_INPUT_REQUIRED),
            "program": None,
            "pages": [],
            "source_urls": [],
        }

    monkeypatch.setattr(appraisal_jobs, "collect_domain_proposal", collect)
    with SessionLocal() as db:
        job, project = _job(db, "network-one-retry.example")
        result = appraisal_jobs._collect_terms(db, job, project)

    assert calls == 2
    assert result["status"] == "MANUAL_INPUT_REQUIRED"
