from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_top_traffic_countries_are_localized_instead_of_showing_raw_json() -> None:
    javascript = (ROOT / "apps/web/app.js").read_text(encoding="utf-8")

    assert "function formatTrafficCountries(rawValue)" in javascript
    assert 'new Intl.DisplayNames(["vi"], {type: "region"})' in javascript
    assert 'metricItem.key === "top_traffic_countries"' in javascript
    assert 'rows.join(" · ")' in javascript


def test_technical_metric_labels_have_vietnamese_display_names() -> None:
    javascript = (ROOT / "apps/web/app.js").read_text(encoding="utf-8")

    assert 'top_traffic_countries: "Quốc gia có traffic cao nhất"' in javascript
    assert 'active_advertisers_30d: "Nhà quảng cáo đang chạy 7 ngày"' in javascript
    assert "displayMetricLabel(metricItem)" in javascript
