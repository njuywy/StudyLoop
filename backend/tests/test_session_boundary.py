from fastapi.testclient import TestClient

from studyloop.main import create_app
from studyloop.settings import Settings


def test_missing_and_malformed_bearer_are_rejected_without_database_or_leak():
    with TestClient(create_app(Settings())) as client:
        for authorization in (None, "Basic secret", "Bearer ", "Bearer " + "secret" * 100):
            headers = {"Authorization": authorization} if authorization is not None else {}
            response = client.get("/api/v1/me", headers=headers)
            assert response.status_code == 401
            assert response.json()["code"] == "UNAUTHORIZED"
            assert "secret" not in response.text
            assert response.headers["cache-control"] == "no-store"
