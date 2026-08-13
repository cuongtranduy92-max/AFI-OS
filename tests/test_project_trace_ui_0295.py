from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_trace_and_saved_portfolio_filter_are_separate_actions() -> None:
    page = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="projectTraceForm"' in page
    assert 'name="domain"' in page
    assert "Bước 1 · Check dự án" in page
    assert 'id="appraisalBatchToggle"' in page
    assert 'id="appraisalResult"' in page
    assert 'id="portfolioFilters"' in page
    assert 'name="query"' in page
    assert "Lọc hồ sơ đã lưu" in page
    assert "Lọc danh sách" in page


def test_trace_submit_uses_stable_appraisal_contract() -> None:
    script = (ROOT / "apps" / "web" / "app.js").read_text(encoding="utf-8")
    trace_block = script.split("async function tracePortfolioProject", 1)[1].split(
        "async function", 1
    )[0]
    intake_block = script.split("async function intakePortfolioProject", 1)[1].split(
        "async function tracePortfolioProject", 1
    )[0]

    assert "normalizeProjectDomainCandidate" in trace_block
    assert "intakePortfolioProject(domain, button, message)" in trace_block
    assert 'request("/appraise"' in intake_block
    assert "Đang check" in intake_block
    assert "appraisalPendingLabels" in intake_block
    assert "renderAppraisal" in intake_block
    assert "filters.reset()" in intake_block
    assert "filters.elements.query.value = domain" in intake_block


def test_trace_form_has_dedicated_submit_listener() -> None:
    script = (ROOT / "apps" / "web" / "app.js").read_text(encoding="utf-8")

    assert 'getElementById("projectTraceForm").addEventListener("submit"' in script
    assert "tracePortfolioProject(event.currentTarget)" in script


def test_appraisal_ui_has_ten_cards_batch_and_step_two_action() -> None:
    script = (ROOT / "apps" / "web" / "app.js").read_text(encoding="utf-8")

    assert "function renderAppraisal" in script
    assert 'appraisalCard(10, "Lượt tìm kiếm"' in script
    assert "async function runAppraisalBatch" in script
    assert "data-appraisal-save" in script
    assert "PREPARE_STEP_2" in script
