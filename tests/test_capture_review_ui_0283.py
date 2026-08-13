from pathlib import Path


def test_web_capture_can_defer_identity_and_review_is_deliberate() -> None:
    page = Path("apps/web/index.html").read_text(encoding="utf-8")
    script = Path("apps/web/app.js").read_text(encoding="utf-8")

    advertiser_field = page.split('name="advertiser_name"', maxsplit=1)[1].split(
        ">", maxsplit=1
    )[0]
    domain_field = page.split('name="project_domain"', maxsplit=1)[1].split(
        ">", maxsplit=1
    )[0]
    assert "required" not in advertiser_field
    assert "required" not in domain_field
    assert 'id="captureSubmit"' in page
    assert "Lưu để duyệt sau" in page
    assert 'id="captureReviewMessage"' in page

    assert "Xem đầy đủ evidence" in script
    assert "window.prompt(" in script
    assert "payload.reason = reason.trim()" in script
    assert 'row.querySelectorAll("button, input")' in script
    assert 'row.setAttribute("aria-busy", "true")' in script
    assert "Đã loại snapshot" in script


def test_chrome_helper_can_send_unstructured_capture() -> None:
    page = Path("tools/ads-transparency-capture/popup.html").read_text(encoding="utf-8")
    script = Path("tools/ads-transparency-capture/popup.js").read_text(encoding="utf-8")

    advertiser_field = page.split('name="advertiser_name"', maxsplit=1)[1].split(
        ">", maxsplit=1
    )[0]
    domain_field = page.split('name="project_domain"', maxsplit=1)[1].split(
        ">", maxsplit=1
    )[0]
    assert "required" not in advertiser_field
    assert "required" not in domain_field
    assert "hàng đợi duyệt" in page
    assert 'capture_method: "chrome-extension-review-queue-v2"' in script
    assert 'result.status === "NEEDS_REVIEW"' in script
    assert "Đang chờ duyệt advertiser/domain" in script
