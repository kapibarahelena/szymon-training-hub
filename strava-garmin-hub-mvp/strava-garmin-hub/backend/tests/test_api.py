from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def test_health_and_auth_boundary():
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/v1/dashboard').status_code == 401
        response = client.get('/api/v1/dashboard', headers={'X-Hub-API-Key': settings.hub_api_key})
        assert response.status_code == 200
        assert 'recent_activities' in response.json()

def test_metric_ingest_is_idempotent():
    payload = {
        "source": "home_assistant",
        "items": [{
            "metric": "weight", "value": 77.9, "unit": "kg",
            "measured_at": "2026-10-25T10:00:00+00:00",
            "source_entity_id": "sensor.garmin_connect_waga",
            "attributes": {"friendly_name": "Waga"},
        }],
    }
    headers = {"X-Hub-API-Key": settings.hub_api_key}
    with TestClient(app) as client:
        first = client.post("/api/v1/metrics/ingest", json=payload, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["inserted"] == 1
        second = client.post("/api/v1/metrics/ingest", json=payload, headers=headers)
        assert second.status_code == 200, second.text
        assert second.json()["inserted"] == 0
        assert second.json()["updated"] == 1


def test_metric_ingest_requires_api_key():
    with TestClient(app) as client:
        response = client.post("/api/v1/metrics/ingest", json={"items": [{
            "metric": "weight", "value": 77.9, "unit": "kg",
            "measured_at": "2026-10-25T10:00:00+00:00",
            "source_entity_id": "sensor.garmin_connect_waga",
        }]})
        assert response.status_code == 401


def test_metric_history_filters_and_paginates():
    headers = {'X-Hub-API-Key': settings.hub_api_key}
    base = {
        "source": "home_assistant",
        "items": [
            {"metric": "weight", "value": 78.0, "unit": "kg", "measured_at": "2026-10-23T08:00:00+00:00", "source_entity_id": "sensor.garmin_connect_waga"},
            {"metric": "weight", "value": 77.9, "unit": "kg", "measured_at": "2026-10-25T08:00:00+00:00", "source_entity_id": "sensor.garmin_connect_waga"},
            {"metric": "sleep_duration", "value": 7.5, "unit": "h", "measured_at": "2026-10-25T07:00:00+00:00", "source_entity_id": "sensor.szymon_czas_snu"},
        ],
    }
    with TestClient(app) as client:
        ingest = client.post('/api/v1/metrics/ingest', json=base, headers=headers)
        assert ingest.status_code == 200, ingest.text
        response = client.get('/api/v1/metrics/history', params={"metric": "weight", "source": "home_assistant", "limit": 1}, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] >= 2
        assert len(data["items"]) == 1
        assert data["items"][0]["value"] == 77.9
        assert data["items"][0]["source_entity_id"] == "sensor.garmin_connect_waga"


def test_metric_history_requires_api_key():
    with TestClient(app) as client:
        assert client.get('/api/v1/metrics/history').status_code == 401
