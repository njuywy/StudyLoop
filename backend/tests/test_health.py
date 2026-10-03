import psycopg
from fastapi.testclient import TestClient

from studyloop import database, main
from studyloop.settings import Settings


def test_health_http_contract_when_database_check_succeeds(monkeypatch):
    # This tests HTTP behavior, not a real PostgreSQL connection (see test_postgres.py).
    monkeypatch.setattr(main, "check_database", lambda _: True)
    with TestClient(main.create_app(Settings())) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_database_errors_produce_safe_unavailable_response(monkeypatch):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError("secret password in database connection")

    monkeypatch.setattr(database.psycopg, "connect", fail)
    with TestClient(main.create_app(Settings(database_url="postgresql://secret"))) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {
        "code": "DATABASE_UNAVAILABLE",
        "message": "平台连接暂不可用，请稍后重试。",
    }
    assert "secret" not in response.text


def test_unconfigured_database_is_not_reported_healthy():
    with TestClient(main.create_app(Settings())) as client:
        assert client.get("/api/v1/health").status_code == 503
