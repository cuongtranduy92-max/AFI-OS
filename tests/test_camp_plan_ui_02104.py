from fastapi.testclient import TestClient

from afi_os.main import app

client = TestClient(app)


def test_step_two_camp_builder_is_exposed_in_local_ui() -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "CLAUDE TERMS · v0.2.107" in page.text
    assert 'id="campPlanWorkspace"' in page.text
    assert 'id="campPlanRefUrl"' in page.text
    assert 'id="campPlanAdsAccount"' in page.text
    assert 'id="campPlanHeadlines"' in page.text
    assert 'id="campPlanDescriptions"' in page.text
    assert 'id="campPlanSitelinks"' in page.text
    assert 'id="campPlanCallouts"' in page.text
    assert 'id="campPlanRelint"' in page.text
    assert 'id="campPlanDeploy"' in page.text
    assert 'id="campPlanStepThree"' in page.text
    assert "/app.js?v=02107" in page.text


def test_step_two_javascript_uses_pass_list_and_safe_deploy_flow() -> None:
    script = client.get("/app.js")
    assert script.status_code == 200
    assert 'request("/projects/camp-plan/eligible")' in script.text
    assert "/camp-plan/generate" in script.text
    assert "/camp-plan/deploy" in script.text
    assert "collectCampPlanEditor" in script.text
    assert "existing_plan" in script.text
    assert "Không có thao tác ghi Google Ads" in script.text
    assert 'request("/ads-accounts/selectable")' in script.text
    assert "button.disabled = true" in script.text
