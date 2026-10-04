from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from test_password_reset import login
from test_password_reset import reset_api as reset_api

from studyloop.main import create_app
from studyloop.registration import connect
from studyloop.sessions import current_user
from studyloop.settings import Settings


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/points/p/state"),
        ("patch", "/points/p/state"),
        ("get", "/books/b/points?filter=bookmarked"),
    ],
)
def test_private_state_requires_authentication(method, path):
    with TestClient(create_app(Settings())) as client:
        result = getattr(client, method)("/api/v1/me/review" + path)
    assert result.status_code == 401 and result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"bookmarked": None},
        {"bookmarked": 1},
        {"bookmarked": "true"},
        {"mastery": None},
        {"mastery": "automatic"},
        {"mastery": "unlearned", "user_id": "other"},
        {"bookmarked": True, "expected_revision": -1},
        {"mastery": "mastered", "operation_id": "bad"},
    ],
)
def test_invalid_state_fields_rejected_without_database(change):
    app = create_app(Settings())
    app.dependency_overrides[current_user] = lambda: {"id": "verified"}
    with TestClient(app) as client:
        result = client.patch(
            "/api/v1/me/review/points/p/state",
            json={"expected_revision": 0, "operation_id": str(uuid4()), **change},
        )
    assert result.status_code == 422 and result.json()["code"] == "INVALID_REVIEW_INPUT"


@pytest.fixture
def review_data(reset_api):
    client, _, settings, _, _, email, account, _ = reset_api
    books = [uuid4().hex, uuid4().hex]
    points = [uuid4().hex for _ in range(23)]
    headers = {"Authorization": "Bearer " + login(client, email).json()["token"]}
    with connect(settings) as connection:
        for book in books:
            connection.execute(
                "INSERT INTO review_books(id,metadata,toc,storage_key,pages) "
                "VALUES(%s,%s,%s,%s,%s)",
                (book, Jsonb({}), Jsonb([]), "unused", Jsonb({})),
            )
        for i, point in enumerate(points):
            connection.execute(
                "INSERT INTO review_points(id,book_id,ordinal,document) VALUES(%s,%s,%s,%s)",
                (
                    point,
                    books[0] if i < 22 else books[1],
                    i,
                    Jsonb({"title": "同名知识点", "path": ["章节" + str(i), "同名知识点"]}),
                ),
            )
    try:
        yield client, settings, headers, account, books, points
    finally:
        with connect(settings) as connection:
            connection.execute("DELETE FROM review_points WHERE book_id=ANY(%s)", (books,))
            connection.execute("DELETE FROM review_books WHERE id=ANY(%s)", (books,))


def url(point):
    return "/api/v1/me/review/points/" + point + "/state"


def patch(client, headers, point, revision, **fields):
    return client.patch(
        url(point),
        headers=headers,
        json={"expected_revision": revision, "operation_id": str(uuid4()), **fields},
    )


@pytest.mark.postgres
def test_independent_state_all_transitions_replay_and_persistence(review_data):
    client, settings, headers, account, _, points = review_data
    point = points[0]
    original = client.get(url(point), headers=headers).json()
    assert original == {
        "point_id": point,
        "bookmarked": False,
        "mastery": "unlearned",
        "revision": 0,
    }
    revision = 0
    for start, end in permutations(["unlearned", "needs_review", "mastered"], 2):
        for mastery in [start, end]:
            result = patch(client, headers, point, revision, mastery=mastery)
            assert result.status_code == 200
            revision += 1
            assert result.json() == {**original, "mastery": mastery, "revision": revision}
    bookmark_body = {
        "bookmarked": True,
        "expected_revision": revision,
        "operation_id": str(uuid4()),
    }
    bookmarked = client.patch(url(point), headers=headers, json=bookmark_body)
    assert bookmarked.json()["mastery"] == mastery
    assert client.patch(url(point), headers=headers, json=bookmark_body).json() == bookmarked.json()
    assert (
        client.patch(
            url(point), headers=headers, json={**bookmark_body, "bookmarked": False}
        ).status_code
        == 409
    )
    other = {"Authorization": "Bearer " + login(client, account("b")).json()["token"]}
    assert client.get(url(point), headers=other).json() == original
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(url(point), headers=headers).json() == bookmarked.json()
    assert patch(client, headers, "missing", 0, bookmarked=True).status_code == 404
    changed = patch(client, headers, point, revision + 1, mastery="mastered")
    assert changed.json()["bookmarked"] is True
    removed = patch(client, headers, point, revision + 2, bookmarked=False)
    assert removed.json()["mastery"] == "mastered"
    assert client.patch(url(point), headers=headers, json=bookmark_body).json() == bookmarked.json()
    assert client.get(url(point), headers=headers).json() == removed.json()
    client.post("/api/v1/auth/logout", headers=headers)
    assert patch(client, headers, point, revision + 1, bookmarked=False).status_code == 401


@pytest.mark.postgres
def test_concurrent_partial_patches_and_ordered_scoped_lists(review_data):
    client, _, headers, account, books, points = review_data
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda fields: patch(client, headers, points[0], 0, **fields),
                [{"bookmarked": True}, {"mastery": "needs_review"}],
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    current = client.get(url(points[0]), headers=headers).json()
    for i, point in enumerate(points):
        assert (
            patch(
                client,
                headers,
                point,
                current["revision"] if i == 0 else 0,
                bookmarked=True,
                mastery="needs_review" if i % 2 == 0 else "mastered",
            ).status_code
            == 200
        )
    path = "/api/v1/me/review/books/" + books[0] + "/points"
    first = client.get(path + "?filter=bookmarked", headers=headers).json()
    second = client.get(path + "?filter=bookmarked&page=2", headers=headers).json()
    assert [p["point_id"] for p in first["items"] + second["items"]] == points[:22]
    assert first["total"] == 22 and second["page"] == 2
    needs = client.get(path + "?filter=needs_review", headers=headers).json()
    assert [p["point_id"] for p in needs["items"]] == points[:22:2]
    for point in points[20:22]:
        state = client.get(url(point), headers=headers).json()
        assert patch(client, headers, point, state["revision"], bookmarked=False).status_code == 200
    clamped = client.get(path + "?filter=bookmarked&page=2", headers=headers).json()
    assert clamped["page"] == 1 and clamped["total"] == 20
    state = client.get(url(points[0]), headers=headers).json()
    patch(client, headers, points[0], state["revision"], mastery="unlearned")
    assert points[0] not in [
        p["point_id"]
        for p in client.get(path + "?filter=needs_review", headers=headers).json()["items"]
    ]
    latest = client.get(url(points[0]), headers=headers).json()
    patch(client, headers, points[0], latest["revision"], mastery="needs_review")
    assert (
        client.get(path + "?filter=needs_review", headers=headers).json()["items"][0]["point_id"]
        == points[0]
    )
    other = {"Authorization": "Bearer " + login(client, account("b")).json()["token"]}
    assert client.get(path + "?filter=bookmarked", headers=other).json()["items"] == []
    assert client.get(path + "?filter=bad", headers=headers).status_code == 422
