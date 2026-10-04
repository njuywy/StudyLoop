from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_password_reset import (
    NEW_PASSWORD,
    OLD_PASSWORD,
    link_token,
    login,
    me,
    request_reset,
    reset,
    user,
    wait_for_account_lock,
)
from test_password_reset import reset_api as reset_api

from studyloop import passwords, profile
from studyloop.main import create_app
from studyloop.sessions import current_user
from studyloop.settings import Settings


def change(client, token, old=OLD_PASSWORD, new=NEW_PASSWORD):
    return client.post(
        "/api/v1/me/change-password",
        headers={"Authorization": "Bearer " + token},
        json={"old_password": old, "new_password": new},
    )


def rename(client, token, body):
    return client.patch("/api/v1/me", headers={"Authorization": "Bearer " + token}, json=body)


@pytest.mark.postgres
def test_nickname_boundaries_duplicate_names_and_identity_isolation(reset_api):
    client, _, settings, _, _, email, account, _ = reset_api
    other = account("b")
    token = login(client, email).json()["token"]
    other_before = user(settings, other)
    for nickname in (" 一 ", "名" * 30, other_before["nickname"]):
        response = rename(client, token, {"nickname": nickname})
        assert response.status_code == 200 and response.json()["nickname"] == nickname.strip()
        assert response.headers["cache-control"] == "no-store"
        assert me(client, token).json()["nickname"] == nickname.strip()
    before = user(settings, email)
    for nickname in ("   ", "名" * 31):
        assert rename(client, token, {"nickname": nickname}).status_code == 422
    for field, value in (
        ("id", str(other_before["id"])),
        ("email", other),
        ("role", "admin"),
        ("enabled", False),
    ):
        assert rename(client, token, {"nickname": "越权", field: value}).status_code == 422
    assert user(settings, email) == before and user(settings, other) == other_before


@pytest.mark.postgres
@pytest.mark.parametrize("new_password", [" 密码abcdefgh ", "密" * 128])
def test_password_change_revokes_all_sessions_and_actual_reset_link(reset_api, new_password):
    client, _, settings, _, mailbox, email, account, _ = reset_api
    other = account("b")
    other_session = login(client, other).json()["token"]
    tokens = [login(client, email).json()["token"] for _ in range(2)]
    before = user(settings, email)
    request_reset(client, email)
    reset_token = link_token(mailbox[-1][1])
    assert change(client, tokens[0], old="wrong password").status_code == 400
    for length in (11, 129):
        assert change(client, tokens[0], new="密" * length).status_code == 422
    assert user(settings, email) == before
    assert all(me(client, token).status_code == 200 for token in tokens)
    assert change(client, tokens[0], new=new_password).status_code == 200
    assert all(me(client, token).status_code == 401 for token in tokens)
    assert reset(client, reset_token).status_code == 400
    assert login(client, email).status_code == 401
    assert login(client, email, new_password).status_code == 200
    assert me(client, other_session).status_code == 200


@pytest.mark.postgres
@pytest.mark.parametrize("first_operation", ["change", "reset"])
def test_change_and_reset_serialize_without_reusing_revoked_credentials(
    reset_api, monkeypatch, first_operation
):
    client, _, settings, _, mailbox, email, _, prefix = reset_api
    token = login(client, email).json()["token"]
    request_reset(client, email)
    reset_token = link_token(mailbox[-1][1])
    entered, release = Event(), Event()
    module = profile if first_operation == "change" else passwords
    original = module.replace_password_and_revoke

    def gated_replace(*args):
        original(*args)
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(module, "replace_password_and_revoke", gated_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = (
            pool.submit(change, client, token, OLD_PASSWORD, "first change password")
            if first_operation == "change"
            else pool.submit(reset, client, reset_token, "first reset password")
        )
        try:
            assert entered.wait(5)
            second = (
                pool.submit(reset, client, reset_token, "second reset password")
                if first_operation == "change"
                else pool.submit(change, client, token, OLD_PASSWORD, "second change password")
            )
            wait_for_account_lock(settings, prefix)
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
        assert second.result(timeout=10).status_code == (
            400 if first_operation == "change" else 401
        )
    assert me(client, token).status_code == 401
    assert reset(client, reset_token).status_code == 400
    expected = "first change password" if first_operation == "change" else "first reset password"
    assert login(client, email, expected).status_code == 200


@pytest.mark.postgres
def test_waiting_profile_update_rechecks_session_after_password_reset(reset_api, monkeypatch):
    client, _, settings, _, mailbox, email, _, prefix = reset_api
    token = login(client, email).json()["token"]
    before = user(settings, email)["nickname"]
    request_reset(client, email)
    reset_token = link_token(mailbox[-1][1])
    entered, release = Event(), Event()
    original = passwords.replace_password_and_revoke

    def gated_replace(*args):
        original(*args)
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(passwords, "replace_password_and_revoke", gated_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        resetting = pool.submit(reset, client, reset_token)
        try:
            assert entered.wait(5)
            updating = pool.submit(rename, client, token, {"nickname": "stale update"})
            wait_for_account_lock(settings, prefix)
        finally:
            release.set()
        assert resetting.result(timeout=10).status_code == 200
        assert updating.result(timeout=10).status_code == 401
    assert user(settings, email)["nickname"] == before


@pytest.mark.postgres
def test_change_database_failure_rolls_back_every_credential(reset_api, monkeypatch):
    client, _, settings, _, mailbox, email, _, _ = reset_api
    token = login(client, email).json()["token"]
    before = user(settings, email)
    request_reset(client, email)
    reset_token = link_token(mailbox[-1][1])
    original = profile.replace_password_and_revoke

    def fail(*args):
        original(*args)
        raise psycopg.OperationalError("private database details")

    monkeypatch.setattr(profile, "replace_password_and_revoke", fail)
    response = change(client, token)
    assert response.status_code == 503 and "private" not in response.text
    assert user(settings, email) == before and me(client, token).status_code == 200
    assert reset(client, reset_token).status_code == 200


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PATCH", "/api/v1/me", {"nickname": "  "}),
        ("PATCH", "/api/v1/me", {"nickname": "a", "role": "admin"}),
        (
            "POST",
            "/api/v1/me/change-password",
            {"old_password": "sensitive", "new_password": "short"},
        ),
        (
            "POST",
            "/api/v1/me/change-password",
            {"old_password": "sensitive", "new_password": "x" * 129},
        ),
    ],
)
def test_profile_validation_does_not_echo_secrets(method, path, body, caplog):
    app = create_app(Settings())
    app.dependency_overrides[current_user] = lambda: {"id": "test-id", "digest": "test-digest"}
    with TestClient(app) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == 422 and "sensitive" not in response.text + caplog.text
