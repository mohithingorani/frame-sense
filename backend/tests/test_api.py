import pytest


class TestWebSocketEndpoints:
    def test_health_endpoint_returns_status(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "uptime_seconds" in data

    def test_health_endpoint_includes_database_status(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "database" in data

    def test_roi_endpoint_with_default_limit(self, client):
        response = client.get("/roi")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_roi_endpoint_with_custom_limit(self, client):
        response = client.get("/roi?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5

    def test_roi_endpoint_limit_bounds(self, client):
        response = client.get("/roi?limit=0")
        assert response.status_code == 422
        
        response = client.get("/roi?limit=201")
        assert response.status_code == 422