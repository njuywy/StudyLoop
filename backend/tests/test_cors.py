import pytest
from fastapi.testclient import TestClient

from studyloop.main import create_app
from studyloop.settings import Settings


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH"])
def test_pages_preflight_accepts_authorization_and_content_type(method):
    with TestClient(create_app(Settings())) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://njuywy.github.io",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://njuywy.github.io"
    assert "access-control-allow-credentials" not in response.headers


def test_other_origins_are_not_allowed():
    with TestClient(create_app(Settings())) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://example.org",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["*", "https://njuywy.github.io/StudyLoop/", "null"])
def test_invalid_cors_configuration_is_rejected(monkeypatch, origin):
    monkeypatch.setenv("CORS_ORIGINS", origin)
    with pytest.raises(ValueError, match="exact HTTP"):
        Settings.from_env()
