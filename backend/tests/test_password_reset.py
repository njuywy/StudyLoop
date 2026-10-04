"""Password replacement and revocation are verified against an existing isolated PostgreSQL."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from studyloop import passwords, registration, sessions
from studyloop.mail import MailUnavailable
from studyloop.main import create_app
from studyloop.settings import Settings

OLD_PASSWORD = " original password "
NEW_PASSWORD = " replacement password "


def link_token(link):
    return parse_qs(urlsplit(link).fragment.split("?", 1)[1])["token"][0]


@pytest.fixture
def reset_api(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL missing: real password reset transactions not executed")
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    prefix = uuid4().hex
    settings = Settings(
        database_url=make_conninfo(url, application_name=prefix),
        register_limit=100,
        login_limit=100,
        password_reset_limit=100,
    )
    clock = [datetime.now(UTC)]
    for module in (registration, passwords, sessions):
        monkeypatch.setattr(module, "now", lambda: clock[0])
    verification = []
    mailbox = []
    app = create_app(settings)
    app.state.send_verification = lambda settings, email, link: verification.append(link)
    app.state.send_password_reset = lambda settings, email, link: mailbox.append((email, link))
    with TestClient(app, client=(prefix, 50000)) as client:

        def account(suffix="a", verified=True):
            email = f"{prefix}-{suffix}@example.com"
            assert (
                client.post(
                    "/api/v1/auth/register", json={"email": email, "password": OLD_PASSWORD}
                ).status_code
                == 201
            )
            if verified:
                assert (
                    client.post(
                        "/api/v1/auth/verify-email", json={"token": link_token(verification[-1])}
                    ).status_code
                    == 200
                )
            return email

        email = account()
        yield client, app, settings, clock, mailbox, email, account, prefix
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM users WHERE email LIKE %s", (prefix + "%",))
        keys = [
            registration.digest(f"{entry}:{prefix}")
            for entry in ("register", "login", "password-reset")
        ]
        connection.execute("DELETE FROM auth_rate_limits WHERE key = ANY(%s)", (keys,))


def login(client, email, password=OLD_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def request_reset(client, email):
    return client.post("/api/v1/auth/request-password-reset", json={"email": email})


def reset(client, token, password=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": password}
    )


def user(settings, email):
    with registration.connect(settings) as connection:
        return connection.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()


def me(client, token):
    return client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})


def wait_for_account_lock(settings, application_name):
    deadline = time.monotonic() + 5
    with registration.connect(settings) as connection:
        while time.monotonic() < deadline:
            if connection.execute(
                "SELECT 1 FROM pg_stat_activity "
                "WHERE application_name = %s AND wait_event_type = 'Lock'",
                (application_name,),
            ).fetchone():
                return
            # Refresh statistics for the next observation within this read transaction.
            connection.execute("SELECT pg_stat_clear_snapshot()")
            time.sleep(0.02)
    pytest.fail("Concurrent operation did not wait on the account lock")


@pytest.mark.postgres
@pytest.mark.parametrize("new_password", [" 密码abcdefgh ", "密" * 128])
def test_reset_replaces_password_revokes_all_own_sessions_and_preserves_other_accounts(
    reset_api, new_password, caplog
):
    client, app, settings, clock, mailbox, email, account, _ = reset_api
    other = account("b")
    own_sessions = [login(client, email).json()["token"] for _ in range(2)]
    other_session = login(client, other).json()["token"]
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET role = 'admin' WHERE email = %s", (email,))
    before = user(settings, email)
    assert request_reset(client, " " + email.upper() + " ").status_code == 202
    recipient, link = mailbox[-1]
    assert recipient == email and link.startswith(settings.pages_url + "#/reset-password?token=")
    token = link_token(link)
    with registration.connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM email_tokens WHERE user_id = %s AND purpose = 'reset_password'",
            (before["id"],),
        ).fetchone()
        assert row["digest"] == registration.digest(token) and row["digest"] != token
        assert row["expires_at"] == clock[0] + timedelta(minutes=30)
    assert reset(client, token, new_password).status_code == 200
    assert login(client, email).status_code == 401
    assert login(client, email, new_password).status_code == 200
    assert all(me(client, value).status_code == 401 for value in own_sessions)
    assert me(client, other_session).status_code == 200
    assert reset(client, token).status_code == 400
    after = user(settings, email)
    assert {k: v for k, v in before.items() if k != "password_hash"} == {
        k: v for k, v in after.items() if k != "password_hash"
    }
    assert token not in caplog.text and new_password not in caplog.text


@pytest.mark.postgres
def test_uniform_eligibility_and_state_rechecked_at_consumption(reset_api):
    client, app, settings, _, mailbox, email, account, prefix = reset_api
    pending = account("pending", verified=False)
    disabled = account("disabled")
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET enabled = false WHERE email = %s", (disabled,))
    responses = [
        request_reset(client, address)
        for address in (email, pending, disabled, f"{prefix}-missing@example.com")
    ]
    assert all(r.status_code == 202 and r.json() == responses[0].json() for r in responses)
    assert [recipient for recipient, _ in mailbox] == [email]
    token = link_token(mailbox[-1][1])
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET enabled = false WHERE email = %s", (email,))
    assert reset(client, token).status_code == 400
    assert not user(settings, email)["enabled"]
    with registration.connect(settings) as connection:
        connection.execute(
            "UPDATE users SET enabled = true, email_verified = false WHERE email = %s", (email,)
        )
    assert reset(client, token).status_code == 400
    assert not user(settings, email)["email_verified"]


@pytest.mark.postgres
def test_expired_forged_wrong_purpose_and_invalid_password_have_no_side_effects(reset_api):
    client, _, settings, clock, mailbox, email, account, _ = reset_api
    session = login(client, email).json()["token"]
    before = user(settings, email)
    account("pending", verified=False)
    # The verification token has the correct random shape but a different purpose.
    with registration.connect(settings) as connection:
        connection.execute(
            "UPDATE email_tokens SET digest = %s WHERE user_id = %s AND purpose = 'verify_email'",
            (registration.digest("verification-only"), before["id"]),
        )
    assert request_reset(client, email).status_code == 202
    token = link_token(mailbox[-1][1])
    for invalid in ("forged", "verification-only"):
        assert reset(client, invalid).status_code == 400
    for length in (11, 129):
        assert reset(client, token, "密" * length).status_code == 422
    clock[0] += timedelta(minutes=30)
    assert reset(client, token).status_code == 400
    assert user(settings, email) == before
    assert me(client, session).status_code == 200


@pytest.mark.postgres
def test_failed_send_preserves_old_link_success_replaces_it(reset_api):
    client, app, settings, _, mailbox, email, _, _ = reset_api
    request_reset(client, email)
    old = link_token(mailbox[-1][1])
    sender = app.state.send_password_reset

    def fail(*args):
        raise MailUnavailable()

    app.state.send_password_reset = fail
    failed = request_reset(client, email)
    assert failed.status_code == 202 and len(mailbox) == 1
    with registration.connect(settings) as connection:
        assert (
            connection.execute(
                "SELECT consumed_at FROM email_tokens WHERE digest = %s",
                (registration.digest(old),),
            ).fetchone()["consumed_at"]
            is None
        )
    assert reset(client, old).status_code == 200
    app.state.send_password_reset = sender
    request_reset(client, email)
    middle = link_token(mailbox[-1][1])
    request_reset(client, email)
    newest = link_token(mailbox[-1][1])
    assert reset(client, old).status_code == reset(client, middle).status_code == 400
    assert reset(client, newest).status_code == 200


@pytest.mark.postgres
def test_concurrent_consumption_succeeds_once(reset_api):
    client, _, _, _, mailbox, email, _, _ = reset_api
    session = login(client, email).json()["token"]
    request_reset(client, email)
    token = link_token(mailbox[-1][1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda password: reset(client, token, password),
                ["new password one", "new password two"],
            )
        )
    assert sorted(r.status_code for r in results) == [200, 400]
    assert me(client, session).status_code == 401
    winner = "new password one" if results[0].status_code == 200 else "new password two"
    assert login(client, email, winner).status_code == 200


@pytest.mark.postgres
@pytest.mark.parametrize("send_fails", [False, True])
def test_reset_waits_for_send_and_never_reactivates_replaced_link(reset_api, send_fails):
    client, app, settings, _, mailbox, email, _, prefix = reset_api
    request_reset(client, email)
    old = link_token(mailbox[-1][1])
    entered, release = Event(), Event()
    sender = app.state.send_password_reset

    def gated_sender(*args):
        entered.set()
        assert release.wait(10)
        if send_fails:
            raise MailUnavailable()
        sender(*args)

    app.state.send_password_reset = gated_sender
    with ThreadPoolExecutor(max_workers=2) as pool:
        sending = pool.submit(request_reset, client, email)
        try:
            assert entered.wait(5)
            consuming = pool.submit(reset, client, old)
            wait_for_account_lock(settings, prefix)
        finally:
            release.set()
        assert sending.result(timeout=10).status_code == 202
        assert consuming.result(timeout=10).status_code == (200 if send_fails else 400)
    if not send_fails:
        assert reset(client, link_token(mailbox[-1][1])).status_code == 200
    assert reset(client, old).status_code == 400


@pytest.mark.postgres
def test_send_after_reset_issues_only_a_fresh_link(reset_api, monkeypatch):
    client, _, settings, _, mailbox, email, _, prefix = reset_api
    request_reset(client, email)
    old = link_token(mailbox[-1][1])
    entered, release = Event(), Event()
    original = passwords.replace_password_and_revoke

    def gated_replace(*args):
        original(*args)
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(passwords, "replace_password_and_revoke", gated_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        consuming = pool.submit(reset, client, old)
        try:
            assert entered.wait(5)
            sending = pool.submit(request_reset, client, email)
            wait_for_account_lock(settings, prefix)
        finally:
            release.set()
        assert consuming.result(timeout=10).status_code == 200
        assert sending.result(timeout=10).status_code == 202
    assert reset(client, old).status_code == 400
    assert reset(client, link_token(mailbox[-1][1])).status_code == 200


@pytest.mark.postgres
def test_concurrent_send_keeps_only_latest_successful_link(reset_api):
    client, app, settings, _, mailbox, email, _, prefix = reset_api
    entered, release = Event(), Event()
    sender = app.state.send_password_reset

    def gated_sender(*args):
        entered.set()
        assert release.wait(10)
        sender(*args)

    app.state.send_password_reset = gated_sender
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request_reset, client, email)
        try:
            assert entered.wait(5)
            second = pool.submit(request_reset, client, email)
            wait_for_account_lock(settings, prefix)
        finally:
            release.set()
        assert first.result(timeout=10).status_code == second.result(timeout=10).status_code == 202
    assert len(mailbox) == 2
    assert reset(client, link_token(mailbox[0][1])).status_code == 400
    assert reset(client, link_token(mailbox[1][1])).status_code == 200


@pytest.mark.postgres
def test_database_failure_rolls_back_password_token_and_sessions(reset_api, monkeypatch):
    client, _, settings, _, mailbox, email, _, _ = reset_api
    session = login(client, email).json()["token"]
    before = user(settings, email)
    request_reset(client, email)
    token = link_token(mailbox[-1][1])
    original = passwords.replace_password_and_revoke

    def fail(*args):
        original(*args)
        raise psycopg.OperationalError("private transaction detail")

    monkeypatch.setattr(passwords, "replace_password_and_revoke", fail)
    response = reset(client, token)
    assert response.status_code == 503 and "private" not in response.text
    assert user(settings, email) == before and me(client, session).status_code == 200
    monkeypatch.setattr(passwords, "replace_password_and_revoke", original)
    assert reset(client, token).status_code == 200


@pytest.mark.postgres
def test_reset_entry_limit_persists_and_expires(reset_api):
    client, app, settings, clock, mailbox, email, _, prefix = reset_api
    app.state.settings = replace(settings, password_reset_limit=1)
    assert request_reset(client, email).status_code == 202
    with TestClient(
        create_app(replace(settings, password_reset_limit=1)), client=(prefix, 50000)
    ) as other:
        assert request_reset(other, email).status_code == 429
    assert len(mailbox) == 1
    clock[0] += timedelta(minutes=10)
    assert request_reset(client, email).status_code == 202


@pytest.mark.parametrize(
    "body",
    [
        {"token": "sensitive-token", "new_password": "secret"},
        {"token": "sensitive-token", "new_password": "x" * 129},
        {"token": "sensitive-token", "new_password": NEW_PASSWORD, "enabled": True},
        {"token": "x" * 129, "new_password": NEW_PASSWORD},
    ],
)
def test_invalid_reset_input_is_redacted_before_database(body, caplog):
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/auth/reset-password", json=body)
    assert response.status_code == 422
    assert "sensitive-token" not in response.text + caplog.text
    assert NEW_PASSWORD not in response.text + caplog.text


def test_password_reset_configuration_and_database_failure():
    with pytest.raises(ValueError):
        Settings(password_reset_limit=0)
    with TestClient(create_app(Settings())) as client:
        response = request_reset(client, "valid@example.com")
    assert response.status_code == 503 and response.json()["code"] == "DATABASE_UNAVAILABLE"
