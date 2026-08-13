from fastapi.testclient import TestClient

from afi_os.db import Base, engine
from afi_os.main import app

client = TestClient(app)


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_capture_is_idempotent_and_builds_radar() -> None:
    payload = {
        "source_url": "https://adstransparency.google.com/demo",
        "page_title": "Demo",
        "selected_text": "Advertiser demo evidence",
        "advertiser_name": "Demo Advertiser",
        "advertiser_location": "US",
        "project_domain": "example-ai.com",
        "brand_name": "Example AI",
        "category": "AI",
        "headline": "Example ad",
        "landing_domain": "reviewer.example",
        "country": "US",
    }
    first = client.post("/api/ad-intelligence/captures", json=payload)
    second = client.post("/api/ad-intelligence/captures", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    radar = client.get("/api/ad-intelligence/radar")
    assert radar.status_code == 200
    assert radar.json()[0]["domain"] == "example-ai.com"
    assert radar.json()[0]["distinct_advertisers"] == 1
