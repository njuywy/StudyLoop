from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_password_reset import login
from test_password_reset import reset_api as reset_api
from test_review import bundle as bundle

from studyloop import positions
from studyloop.content_import import publish_bundle, validate_bundle
from studyloop.main import create_app
from studyloop.registration import connect
from studyloop.sessions import current_user
from studyloop.settings import Settings


def payload(point):
    return {
        "point_id": point["id"],
        "block_id": point["blocks"][0]["id"],
        "offset": 0.4,
        "content_version": point["version"],
        "expected_revision": 0,
        "operation_id": str(uuid4()),
    }


@pytest.mark.parametrize("method", ["get", "put"])
def test_position_requires_authentication(method):
    with TestClient(create_app(Settings())) as client:
        response = getattr(client, method)("/api/v1/me/review/books/book/position")
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "change",
    [
        {"offset": -0.1},
        {"offset": 1.1},
        {"offset": True},
        {"offset": "0.5"},
        {"expected_revision": -1},
        {"expected_revision": True},
        {"operation_id": "bad"},
        {"point_id": "bad"},
        {"block_id": "bad"},
        {"content_version": "bad"},
        {"user_id": "other"},
    ],
)
def test_invalid_position_rejected_before_database(change):
    app = create_app(Settings())
    app.dependency_overrides[current_user] = lambda: {"id": "verified"}
    body = {
        "point_id": "a" * 32,
        "block_id": "b" * 32,
        "content_version": "c" * 64,
        "offset": 0.5,
        "expected_revision": 0,
        "operation_id": str(uuid4()),
        **change,
    }
    with TestClient(app) as client:
        response = client.put("/api/v1/me/review/books/book/position", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REVIEW_INPUT"


@pytest.fixture
def positioned(reset_api, bundle, tmp_path):
    client, app, settings, _, _, email, account, _ = reset_api
    settings = replace(settings, review_directory=str(tmp_path / "private"))
    app.state.settings = settings
    book = publish_bundle(bundle, settings)
    headers = {"Authorization": "Bearer " + login(client, email).json()["token"]}
    try:
        yield (
            client,
            settings,
            headers,
            account,
            "/api/v1/me/review/books/" + book["id"] + "/position",
            validate_bundle(bundle)["points"],
        )
    finally:
        with connect(settings) as connection:
            connection.execute("DELETE FROM review_points WHERE book_id=%s", (book["id"],))
            connection.execute("DELETE FROM review_books WHERE id=%s", (book["id"],))


@pytest.mark.postgres
def test_position_persistence_identity_validation_and_replay(positioned):
    client, settings, headers, account, path, points = positioned
    assert client.get(path, headers=headers).json() == {"position": None}
    body = payload(points[0])
    first = client.put(path, headers=headers, json=body)
    assert first.status_code == 200 and first.json()["position"]["revision"] == 1
    assert client.put(path, headers=headers, json=body).json() == first.json()
    assert client.put(path, headers=headers, json={**body, "offset": 0.9}).status_code == 409
    for change, status in [
        ({"block_id": "a" * 32}, 422),
        ({"point_id": "b" * 32}, 404),
        ({"content_version": "c" * 64}, 422),
    ]:
        response = client.put(
            path,
            headers=headers,
            json={**body, "operation_id": str(uuid4()), "expected_revision": 1, **change},
        )
        assert response.status_code == status
    assert (
        client.put(
            path.replace(path.split("/")[-2], "unrelated-book"), headers=headers, json=body
        ).status_code
        == 404
    )
    other = {"Authorization": "Bearer " + login(client, account("b")).json()["token"]}
    assert client.get(path, headers=other).json() == {"position": None}
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path, headers=headers).json() == first.json()
    assert client.get(path, headers=headers).headers["cache-control"] == "no-store"


@pytest.mark.postgres
def test_concurrent_positions_do_not_overwrite_and_old_replays_do_not_advance(positioned):
    client, _, headers, _, path, points = positioned
    bodies = [payload(p) for p in points[:2]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: client.put(path, headers=headers, json=body), bodies))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(i for i, r in enumerate(results) if r.status_code == 200)
    latest = client.put(path, headers=headers, json={**payload(points[-1]), "expected_revision": 1})
    assert latest.json()["position"]["revision"] == 2
    assert client.put(path, headers=headers, json=bodies[winner]).json() == results[winner].json()
    assert client.get(path, headers=headers).json() == latest.json()


@pytest.mark.postgres
def test_revocation_before_position_commit_is_rechecked(positioned, monkeypatch):
    client, settings, headers, _, path, points = positioned
    entered, release = Event(), Event()
    original = positions.lock_current_user

    def gated(connection, user):
        entered.set()
        assert release.wait(5)
        return original(connection, user)

    monkeypatch.setattr(positions, "lock_current_user", gated)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.put, path, headers=headers, json=payload(points[0]))
        assert entered.wait(5)
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        release.set()
        assert pending.result().status_code == 401
    with connect(settings) as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS n FROM review_positions WHERE book_id=%s",
                (path.split("/")[-2],),
            ).fetchone()["n"]
            == 0
        )
