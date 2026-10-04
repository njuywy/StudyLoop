import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_password_reset import login, me, user
from test_password_reset import reset_api as reset_api

from studyloop import admin, registration
from studyloop.main import create_app
from studyloop.sessions import current_user
from studyloop.settings import Settings

FIELDS = {"id", "email", "nickname", "role", "email_verified", "enabled", "created_at"}


def grant(settings, email):
    return subprocess.run(
        [sys.executable, "-m", "studyloop.cli", "grant-admin", email],
        env={
            **os.environ,
            "DATABASE_URL": settings.database_url,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
        text=True,
        capture_output=True,
        timeout=15,
    )


def listing(client, token, **params):
    return client.get(
        "/api/v1/admin/users", headers={"Authorization": "Bearer " + token}, params=params
    )


def status(client, token, target, enabled):
    return client.patch(
        f"/api/v1/admin/users/{target}/status",
        headers={"Authorization": "Bearer " + token},
        json={"enabled": enabled},
    )


@pytest.fixture
def admin_api(reset_api):
    client, app, settings, _, _, email, account, prefix = reset_api
    # Prepare through real registration+verification, then invoke the real command.
    assert grant(settings, email).returncode == 0
    token = login(client, email).json()["token"]
    return client, app, settings, email, token, account, prefix


@pytest.mark.postgres
def test_cli_eligibility_idempotence_and_live_role_authorization(reset_api):
    client, _, settings, _, _, email, account, prefix = reset_api
    token = login(client, email).json()["token"]
    assert listing(client, token).status_code == 403
    assert grant(settings, " " + email.upper() + " ").returncode == 0
    assert grant(settings, email).returncode == 0
    assert user(settings, email)["role"] == "admin"
    assert listing(client, token).status_code == 200
    pending = account("pending", verified=False)
    disabled = account("disabled")
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET enabled = false WHERE email = %s", (disabled,))
    for address in (pending, disabled, prefix + "-missing@example.com"):
        before = user(settings, address)
        result = grant(settings, address)
        assert result.returncode == 1 and "账号必须存在" in result.stderr
        assert user(settings, address) == before
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": prefix + "-injected@example.com",
            "password": "long enough password",
            "role": "admin",
        },
    )
    assert response.status_code == 422
    assert user(settings, prefix + "-injected@example.com") is None
    with registration.connect(settings) as connection:
        connection.execute("UPDATE users SET role = 'user' WHERE email = %s", (email,))
    assert listing(client, token).status_code == 403


@pytest.mark.postgres
def test_pagination_snapshot_order_boundaries_and_public_fields(admin_api):
    client, _, settings, _, token, account, _ = admin_api
    for number in range(20):
        account("page-" + str(number))
    with registration.connect(settings) as connection:
        expected = [
            str(row["id"])
            for row in connection.execute("SELECT id FROM users ORDER BY created_at, id").fetchall()
        ]
    default = listing(client, token)
    assert default.status_code == 200 and default.headers["cache-control"] == "no-store"
    data = default.json()
    assert data["total"] == len(expected) and data["page_size"] == 20 and data["page"] == 1
    assert [row["id"] for row in data["items"]] == expected[:20]
    assert all(set(row) == FIELDS for row in data["items"])
    second = listing(client, token, page=2).json()
    assert [row["id"] for row in second["items"]] == expected[20:40]
    assert listing(client, token).json() == data
    assert listing(client, token, page_size=100).status_code == 200
    empty = listing(client, token, page=2_147_483_647).json()
    assert empty["items"] == [] and empty["total"] == len(expected)
    for params in (
        {"page": 0},
        {"page": -1},
        {"page": "bad"},
        {"page_size": 0},
        {"page_size": 101},
        {"page_size": -1},
    ):
        assert listing(client, token, **params).status_code == 422


@pytest.mark.postgres
def test_disable_restore_revoke_all_sessions_and_keep_other_accounts(admin_api):
    client, _, settings, _, admin_token, account, _ = admin_api
    email, other = account("user"), account("other")
    before = user(settings, email)
    other_before = user(settings, other)
    tokens = [login(client, email).json()["token"] for _ in range(2)]
    other_token = login(client, other).json()["token"]
    assert listing(client, tokens[0]).status_code == 403
    assert status(client, tokens[0], before["id"], False).status_code == 403
    for _ in range(2):
        response = status(client, admin_token, before["id"], False)
        assert response.status_code == 200 and response.json()["enabled"] is False
        assert set(response.json()) == FIELDS
    assert all(me(client, token).status_code == 401 for token in tokens)
    assert login(client, email).status_code == 401
    assert me(client, other_token).status_code == 200
    assert user(settings, other) == other_before
    for _ in range(2):
        assert status(client, admin_token, before["id"], True).status_code == 200
    assert all(me(client, token).status_code == 401 for token in tokens)
    assert login(client, email).status_code == 200
    assert user(settings, email) == before


@pytest.mark.postgres
def test_protected_admins_missing_targets_and_strict_input(admin_api):
    client, _, settings, email, token, account, _ = admin_api
    other = account("other-admin")
    assert grant(settings, other).returncode == 0
    for address in (email, other):
        before = user(settings, address)
        for enabled in (True, False):
            assert status(client, token, before["id"], enabled).status_code == 400
        assert user(settings, address) == before
    target = user(settings, account("ordinary"))
    for invalid in ("false", 0, 1, None, [], {}):
        assert status(client, token, target["id"], invalid).status_code == 422
    assert status(client, token, uuid4(), False).status_code == 404
    assert status(client, token, "invalid-uuid", False).status_code == 422
    assert user(settings, target["email"]) == target
    assert listing(client, "").status_code == 401
    assert status(client, "invalid", target["id"], False).status_code == 401
    assert client.delete(f"/api/v1/admin/users/{target['id']}").status_code in (404, 405)


@pytest.mark.postgres
def test_disable_failure_rolls_back_status_and_session_revocation(admin_api, monkeypatch):
    client, _, settings, _, token, account, _ = admin_api
    email = account("user")
    before = user(settings, email)
    tokens = [login(client, email).json()["token"] for _ in range(2)]
    real_connect = admin.connect

    @contextmanager
    def fail_commit(settings):
        with real_connect(settings) as connection:
            yield connection
            raise psycopg.OperationalError("private database failure")

    monkeypatch.setattr(admin, "connect", fail_commit)
    response = status(client, token, before["id"], False)
    assert response.status_code == 503 and "private" not in response.text
    assert user(settings, email) == before
    assert all(me(client, value).status_code == 200 for value in tokens)


@pytest.mark.postgres
def test_role_rechecked_after_request_authentication(admin_api, monkeypatch):
    client, _, settings, email, token, account, _ = admin_api
    target = user(settings, account("user"))
    entered, release = Event(), Event()
    original = admin.require_admin
    first_check = True

    def gated_check(user):
        nonlocal first_check
        original(user)
        if first_check:
            first_check = False
            entered.set()
            assert release.wait(10)

    monkeypatch.setattr(admin, "require_admin", gated_check)
    with ThreadPoolExecutor(max_workers=1) as pool:
        changing = pool.submit(status, client, token, target["id"], False)
        try:
            assert entered.wait(5)
            with registration.connect(settings) as connection:
                connection.execute("UPDATE users SET role = 'user' WHERE email = %s", (email,))
        finally:
            release.set()
        assert changing.result(timeout=10).status_code == 403
    assert user(settings, target["email"]) == target


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/v1/admin/users", None),
        ("PATCH", f"/api/v1/admin/users/{uuid4()}/status", {"enabled": False}),
    ],
)
def test_ordinary_user_cannot_reach_admin_database_operations(method, path, body):
    app = create_app(Settings())
    app.dependency_overrides[current_user] = lambda: {"id": uuid4(), "role": "user"}
    with TestClient(app) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == 403 and response.json()["code"] == "ADMIN_REQUIRED"


def test_cli_invalid_email_does_not_echo_input():
    result = grant(Settings(), "sensitive invalid input")
    assert result.returncode == 1 and "sensitive" not in result.stdout + result.stderr
