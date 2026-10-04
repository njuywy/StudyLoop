"""Login/session HTTP and transaction regressions require an isolated PostgreSQL database."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from studyloop import registration, sessions
from studyloop.main import create_app
from studyloop.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.fixture
def session_api(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL missing: real PostgreSQL session tests not executed")
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    prefix = uuid4().hex
    settings = Settings(database_url=url, register_limit=100, resend_limit=100, login_limit=100)
    clock = [datetime.now(UTC)]
    monkeypatch.setattr(registration, "now", lambda: clock[0])
    monkeypatch.setattr(sessions, "now", lambda: clock[0])
    mailbox = []
    app = create_app(settings)
    app.state.send_verification = lambda settings, recipient, link: mailbox.append(link)
    with TestClient(app, client=(prefix, 50000)) as client:
        yield client, settings, clock, mailbox, prefix, app
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM users WHERE email LIKE %s", (prefix + "%",))
        keys = [
            registration.digest(f"{entry}:{prefix}") for entry in ("register", "resend", "login")
        ]
        connection.execute("DELETE FROM auth_rate_limits WHERE key = ANY(%s)", (keys,))


def prepare_user(client, mailbox, prefix, suffix="a"):
    email = f"{prefix}-{suffix}@example.com"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": "password for sessions"}
        ).status_code
        == 201
    )
    token = parse_qs(urlsplit(mailbox[-1]).fragment.split("?", 1)[1])["token"][0]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    return email


def login(client, email, password="password for sessions"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.mark.postgres
def test_login_profile_logout_and_token_digest(session_api, caplog):
    client, settings, clock, mailbox, prefix, app = session_api
    email = prepare_user(client, mailbox, prefix)
    other = prepare_user(client, mailbox, prefix, "b")
    response = login(client, email.upper())
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"token", "expires_at", "user"}
    assert data["user"]["email"] == email and data["user"]["role"] == "user"
    assert datetime.fromisoformat(data["expires_at"]) == clock[0] + timedelta(hours=12)
    raw = data["token"]
    with registration.connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM auth_sessions WHERE digest = %s", (registration.digest(raw),)
        ).fetchone()
        assert row["digest"] != raw and row["revoked_at"] is None
        assert row["expires_at"] == clock[0] + timedelta(hours=12)
        assert connection.execute("SELECT count(*) AS n FROM auth_sessions").fetchone()["n"] >= 1
    headers = {"Authorization": "Bearer " + raw}
    me = client.get("/api/v1/me", headers=headers, params={"user_id": other})
    assert me.status_code == 200 and me.json()["email"] == email
    assert other not in me.text and "password" not in me.text and raw not in me.text
    assert me.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 401
    assert raw not in caplog.text


@pytest.mark.postgres
def test_ineligible_password_and_state_changes_are_rejected(session_api):
    client, settings, clock, mailbox, prefix, app = session_api
    email = prepare_user(client, mailbox, prefix)
    pending = f"{prefix}-pending@example.com"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": pending, "password": "password for sessions"}
        ).status_code
        == 201
    )
    for address, password in (
        (email, "wrong password"),
        (pending, "password for sessions"),
        (f"{prefix}-missing@example.com", "password for sessions"),
    ):
        response = login(client, address, password)
        assert response.status_code == 401 and response.json()["code"] == "INVALID_CREDENTIALS"
        assert "token" not in response.text
    raw = login(client, email).json()["token"]
    headers = {"Authorization": "Bearer " + raw}
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET enabled = false WHERE email = %s", (email,))
    assert login(client, email).status_code == 401
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET enabled = true WHERE email = %s", (email,))
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    raw = login(client, email).json()["token"]
    headers = {"Authorization": "Bearer " + raw}
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET email_verified = false WHERE email = %s", (email,))
    assert client.get("/api/v1/me", headers=headers).status_code == 401


@pytest.mark.postgres
def test_expired_forged_and_malformed_bearer(session_api):
    client, settings, clock, mailbox, prefix, app = session_api
    email = prepare_user(client, mailbox, prefix)
    raw = login(client, email).json()["token"]
    for headers in (
        {},
        {"Authorization": "Basic " + raw},
        {"Authorization": "Bearer forged"},
        {"Authorization": "Bearer " + raw + "extra"},
    ):
        assert client.get("/api/v1/me", headers=headers).status_code == 401
    clock[0] += timedelta(hours=12)
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer " + raw}).status_code == 401


@pytest.mark.postgres
def test_login_limit_persists_across_app_instances(session_api):
    client, settings, clock, mailbox, prefix, app = session_api
    email = prepare_user(client, mailbox, prefix)
    app.state.settings = replace(settings, login_limit=2)
    assert login(client, email, "wrong 1").status_code == 401
    assert login(client, email, "wrong 2").status_code == 401
    with TestClient(create_app(replace(settings, login_limit=2)), client=(prefix, 50000)) as other:
        assert login(other, email).status_code == 429
    clock[0] += timedelta(minutes=10)
    assert login(client, email).status_code == 200
