"""HTTP regressions; PostgreSQL cases require an operator-supplied isolated database."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from studyloop import registration
from studyloop.mail import MailUnavailable
from studyloop.main import create_app
from studyloop.settings import Settings


class Mailbox:
    def __init__(self):
        self.messages = []
        self.fail = False

    def __call__(self, settings, recipient, link):
        if self.fail:
            raise MailUnavailable()
        if link is not None:
            self.messages.append((recipient, link))

    def token(self, index=-1):
        return parse_qs(urlsplit(self.messages[index][1]).fragment.split("?", 1)[1])["token"][0]


@pytest.fixture
def account_api(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL missing: real transaction tests not executed")
    settings = Settings(database_url=url, register_limit=100, resend_limit=100)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    clock = [datetime.now(UTC)]
    monkeypatch.setattr(registration, "now", lambda: clock[0])
    prefix = uuid4().hex
    mailbox = Mailbox()
    app = create_app(settings)
    app.state.send_verification = mailbox
    with TestClient(app, client=(prefix, 50000)) as client:
        yield client, mailbox, settings, clock, prefix
    with psycopg.connect(settings.database_url) as connection:
        emails = connection.execute(
            "SELECT email FROM users WHERE email LIKE %s", (prefix + "%",)
        ).fetchall()
        connection.execute("DELETE FROM users WHERE email LIKE %s", (prefix + "%",))
        keys = [registration.digest(f"{entry}:{prefix}") for entry in ("register", "resend")]
        keys += [registration.digest("resend-email:" + email[0]) for email in emails]
        keys += [registration.digest(f"resend-email:{prefix}-missing@example.com")]
        connection.execute("DELETE FROM auth_rate_limits WHERE key = ANY(%s)", (keys,))


def register(client, prefix, **overrides):
    body = {"email": f"{prefix}@example.com", "password": " a private password "}
    body.update(overrides)
    return client.post("/api/v1/auth/register", json=body)


def user_record(settings, email):
    with registration.connect(settings) as connection:
        return connection.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()


@pytest.mark.postgres
def test_register_deliver_verify_once_preserves_independent_states(account_api):
    client, mailbox, settings, clock, prefix = account_api
    response = register(client, prefix)
    assert response.status_code == 201
    assert set(response.json()) == {"code", "message"}
    assert "set-cookie" not in response.headers
    recipient, link = mailbox.messages[0]
    assert link.startswith("https://njuywy.github.io/StudyLoop/#/verify-email?token=")
    user = user_record(settings, recipient)
    assert user["nickname"] == "学习者"
    assert user["role"] == "user" and user["enabled"] and not user["email_verified"]
    assert user["password_hash"].startswith("$argon2id$")
    assert PasswordHasher().verify(user["password_hash"], " a private password ")
    token = mailbox.token()
    with registration.connect(settings) as connection:
        stored = connection.execute(
            "SELECT * FROM email_tokens WHERE user_id = %s", (user["id"],)
        ).fetchone()
        assert stored["digest"] != token and stored["digest"] == registration.digest(token)
        assert stored["expires_at"] == clock[0] + timedelta(hours=24)
        connection.execute(
            "UPDATE users SET enabled = false, role = 'admin' WHERE id = %s", (user["id"],)
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: client.post("/api/v1/auth/verify-email", json={"token": token}), range(2)
            )
        )
    assert sorted(r.status_code for r in results) == [200, 400]
    assert all("set-cookie" not in r.headers for r in results)
    after = user_record(settings, recipient)
    assert after["email_verified"] and not after["enabled"] and after["role"] == "admin"


@pytest.mark.postgres
@pytest.mark.parametrize("length,expected", [(11, 422), (12, 201), (128, 201), (129, 422)])
def test_password_boundaries(account_api, length, expected):
    client, mailbox, settings, _, prefix = account_api
    assert register(client, prefix, password="密" * length).status_code == expected
    assert bool(user_record(settings, f"{prefix}@example.com")) == (expected == 201)


@pytest.mark.postgres
def test_duplicate_normalization_concurrency_does_not_overwrite(account_api):
    client, mailbox, settings, _, prefix = account_api
    assert register(client, prefix, nickname="  原昵称  ").status_code == 201
    before = user_record(settings, f"{prefix}@example.com")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: register(
                    client,
                    prefix,
                    email=f" {prefix.upper()}@EXAMPLE.COM ",
                    password="replacement password",
                    nickname="覆盖",
                ),
                range(2),
            )
        )
    assert [r.status_code for r in results] == [409, 409]
    assert user_record(settings, f"{prefix}@example.com") == before
    assert before["nickname"] == "原昵称" and len(mailbox.messages) == 1
    fresh_email = f"{prefix}-fresh@example.com"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: register(client, prefix, email=fresh_email), range(2))
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert register(client, prefix, role="admin").status_code == 422
    assert user_record(settings, fresh_email)["role"] == "user"


@pytest.mark.postgres
@pytest.mark.parametrize("invalid_kind", ["expired", "wrong-purpose", "forged"])
def test_invalid_token_preserves_user(account_api, invalid_kind):
    client, mailbox, settings, clock, prefix = account_api
    register(client, prefix)
    before = user_record(settings, f"{prefix}@example.com")
    token = mailbox.token()
    if invalid_kind == "expired":
        clock[0] += timedelta(hours=24)
    elif invalid_kind == "wrong-purpose":
        with registration.connect(settings) as connection:
            connection.execute(
                "UPDATE email_tokens SET purpose = 'reset_password' WHERE user_id = %s",
                (before["id"],),
            )
    else:
        token = "forged-token"
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    assert user_record(settings, f"{prefix}@example.com") == before


@pytest.mark.postgres
def test_resend_success_replaces_old_failure_preserves_old_and_retry(account_api):
    client, mailbox, settings, clock, prefix = account_api
    register(client, prefix)
    email = f"{prefix}@example.com"
    old = mailbox.token()
    clock[0] += timedelta(seconds=60)
    accepted = client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert accepted.status_code == 202
    new = mailbox.token()
    assert new != old
    assert client.post("/api/v1/auth/verify-email", json={"token": old}).status_code == 400
    assert client.post("/api/v1/auth/resend-verification", json={"email": email}).status_code == 429
    clock[0] += timedelta(seconds=60)
    mailbox.fail = True
    failed = client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert failed.status_code == 503 and failed.json()["code"] == "MAIL_SERVICE_UNAVAILABLE"
    absent = client.post(
        "/api/v1/auth/resend-verification", json={"email": f"{prefix}-missing@example.com"}
    )
    assert absent.status_code == failed.status_code and absent.json() == failed.json()
    with registration.connect(settings) as connection:
        assert connection.execute(
            "SELECT digest FROM email_tokens WHERE user_id = %s",
            (user_record(settings, email)["id"],),
        ).fetchone()["digest"] == registration.digest(new)
    clock[0] += timedelta(seconds=60)
    mailbox.fail = False
    assert client.post("/api/v1/auth/resend-verification", json={"email": email}).status_code == 202
    assert client.post("/api/v1/auth/verify-email", json={"token": new}).status_code == 400
    assert (
        client.post("/api/v1/auth/verify-email", json={"token": mailbox.token()}).status_code == 200
    )


@pytest.mark.postgres
def test_registration_send_failure_retains_account_and_allows_resend(account_api):
    client, mailbox, settings, clock, prefix = account_api
    mailbox.fail = True
    assert register(client, prefix).status_code == 503
    before = user_record(settings, f"{prefix}@example.com")
    assert before and not before["email_verified"]
    assert register(client, prefix, password="another password").status_code == 409
    assert user_record(settings, f"{prefix}@example.com") == before
    mailbox.fail = False
    assert (
        client.post("/api/v1/auth/resend-verification", json={"email": before["email"]}).status_code
        == 202
    )
    assert (
        client.post("/api/v1/auth/verify-email", json={"token": mailbox.token()}).status_code == 200
    )


@pytest.mark.postgres
def test_uniform_resend_and_persistent_ip_limits(account_api, caplog):
    client, mailbox, settings, clock, prefix = account_api
    caplog.set_level(logging.INFO)
    register(client, prefix)
    clock[0] += timedelta(seconds=60)
    present = client.post(
        "/api/v1/auth/resend-verification", json={"email": f"{prefix}@example.com"}
    )
    absent = client.post(
        "/api/v1/auth/resend-verification", json={"email": f"{prefix}-missing@example.com"}
    )
    assert present.status_code == absent.status_code == 202 and present.json() == absent.json()
    for email in (f"{prefix}@example.com", f"{prefix}-missing@example.com"):
        assert (
            client.post("/api/v1/auth/resend-verification", json={"email": email}).status_code
            == 429
        )
    assert mailbox.token() not in caplog.text and "a private password" not in caplog.text
    strict_app = create_app(replace(settings, register_limit=1, resend_limit=1))
    with TestClient(strict_app, client=(prefix, 50000)) as restarted:
        assert register(restarted, prefix).status_code == 429
        assert (
            restarted.post(
                "/api/v1/auth/resend-verification", json={"email": f"{prefix}@example.com"}
            ).status_code
            == 429
        )


@pytest.mark.parametrize(
    "path,body",
    [
        ("register", {"email": "bad", "password": "secret"}),
        ("register", {"email": "valid@example.com", "password": "secret" * 30}),
        (
            "register",
            {"email": "valid@example.com", "password": "a long password", "role": "admin"},
        ),
        ("verify-email", {"token": "secret" * 30}),
        ("resend-verification", {"email": "invalid"}),
    ],
)
def test_invalid_http_input_is_safe_without_database(path, body, caplog):
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/auth/" + path, json=body)
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert "secret" not in response.text + caplog.text


def test_auth_database_error_does_not_leak_credentials():
    with TestClient(create_app(Settings())) as client:
        response = register(client, "test")
    assert response.status_code == 503 and response.json()["code"] == "DATABASE_UNAVAILABLE"
