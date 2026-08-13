from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "apps" / "web" / "app.js"


def test_project_radar_distinguishes_not_collected_from_partial_activity() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert 'item.distinct_advertisers == null ? "Chưa thu thập"' in source
    assert (
        'item.distinct_advertisers == null ? "Chưa thu thập" : "Chưa đủ dữ liệu"'
        in source
    )
    assert 'item.active_advertisers_30d == null ?' in source
    assert 'item.top_advertiser_share == null ?' in source
