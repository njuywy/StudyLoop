import io
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Event

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_password_reset import login, user, wait_for_account_lock
from test_password_reset import reset_api as reset_api

from studyloop import avatars
from studyloop.main import create_app
from studyloop.registration import AuthError
from studyloop.sessions import current_user
from studyloop.settings import Settings


def picture(format="PNG", size=(16, 16), color="red"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format=format)
    return output.getvalue()


def upload(client, token, image_data=None, mime="image/png", name="photo.png", **kwargs):
    return client.put(
        "/api/v1/me/avatar",
        headers={"Authorization": "Bearer " + token},
        files={"file": (name, picture() if image_data is None else image_data, mime)},
        **kwargs,
    )


def read(client, token):
    return client.get("/api/v1/me/avatar", headers={"Authorization": "Bearer " + token})


@pytest.fixture
def avatar_api(reset_api, tmp_path):
    client, app, settings, _, _, email, account, prefix = reset_api
    settings = replace(settings, avatar_directory=str(tmp_path))
    app.state.settings = settings
    token = login(client, email).json()["token"]
    return client, settings, email, token, account, prefix, tmp_path


@pytest.mark.parametrize(
    "format,mime,ext",
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
def test_real_decoder_supported_formats_and_exact_file_limit(format, mime, ext):
    data = picture(format)
    # Legal image plus padding: size accounting is file bytes, not multipart bytes.
    exact = data + bytes(avatars.MAX_BYTES - len(data))
    assert avatars.validate_image(exact, mime) == ext
    with pytest.raises(AuthError) as error:
        avatars.validate_image(exact + b"x", mime)
    assert error.value.status == 413


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
        (b"not a jpeg", "image/jpeg"),
        (picture(), "image/jpeg"),
        (picture()[:40], "image/png"),
        (picture(size=(4001, 4000)), "image/png"),
    ],
)
def test_invalid_images_rejected_at_http_boundary_without_touching_storage(data, mime, tmp_path):
    app = create_app(Settings(avatar_directory=str(tmp_path)))
    app.dependency_overrides[current_user] = lambda: {"id": "unused"}
    with TestClient(app) as client:
        response = upload(client, "boundary", data, mime)
    assert response.status_code == 422 and response.json()["code"] == "INVALID_AVATAR"
    assert not list(tmp_path.iterdir())


def test_animation_decode_budget():
    frames = [Image.new("RGB", (800, 800), (i, 20, 30)) for i in range(26)]
    output = io.BytesIO()
    frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:], lossless=True)
    with pytest.raises(AuthError):
        avatars.validate_image(output.getvalue(), "image/webp")


def test_corrupt_png_checksum_returns_validation_error():
    data = bytearray(picture())
    data[data.index(b"IDAT") + 4] ^= 1
    app = create_app(Settings())
    app.dependency_overrides[current_user] = lambda: {"id": "unused"}
    with TestClient(app) as client:
        response = upload(client, "boundary", bytes(data))
    assert response.status_code == 422 and response.json()["code"] == "INVALID_AVATAR"


@pytest.mark.postgres
def test_formats_replacement_isolation_and_restart(avatar_api):
    client, settings, email, token, account, _, root = avatar_api
    other = account("b")
    other_token = login(client, other).json()["token"]
    assert read(client, token).status_code == 404
    other_data = picture(color="blue")
    assert upload(client, other_token, other_data).status_code == 200
    other_before = user(settings, other)
    for format, mime, ext in [
        ("JPEG", "image/jpeg", "jpg"),
        ("PNG", "image/png", "png"),
        ("WEBP", "image/webp", "webp"),
    ]:
        data = picture(format)
        response = upload(
            client,
            token,
            data,
            mime,
            name="../../other.png",
            data={"user_id": str(other_before["id"])},
        )
        assert response.status_code == 200 and response.content == data
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        row = user(settings, email)
        assert avatars.KEY.fullmatch(row["avatar_key"]) and row["avatar_key"].endswith(ext)
        assert (root / str(row["id"]) / row["avatar_key"]).read_bytes() == data
        assert len(list((root / str(row["id"])).iterdir())) == 1
        with TestClient(create_app(settings)) as restarted:
            assert read(restarted, token).content == data
        assert read(client, other_token).content == other_data
        assert user(settings, other) == other_before
    assert client.get("/api/v1/me/avatar").status_code == 401
    assert upload(client, "invalid").status_code == 401
    assert client.get("/avatars/" + row["avatar_key"]).status_code == 404


@pytest.mark.postgres
def test_http_exact_limit_invalid_input_preserves_existing_avatar(avatar_api):
    client, settings, email, token, _, _, root = avatar_api
    data = picture()
    exact = data + bytes(avatars.MAX_BYTES - len(data))
    assert upload(client, token, exact).status_code == 200
    before = user(settings, email)
    for payload, mime, status in [
        (exact + b"x", "image/png", 413),
        (b"fake", "image/png", 422),
        (data, "image/jpeg", 422),
    ]:
        assert upload(client, token, payload, mime).status_code == status
        assert user(settings, email) == before
        assert read(client, token).content == exact
        assert len(list((root / str(before["id"])).iterdir())) == 1


@pytest.mark.postgres
@pytest.mark.parametrize("fault", ["write", "commit", "lost-commit-response"])
def test_storage_and_commit_failures_do_not_delete_current_file(avatar_api, monkeypatch, fault):
    client, settings, email, token, _, _, root = avatar_api
    old = picture()
    new = picture(color="green")
    assert upload(client, token, old).status_code == 200
    before = user(settings, email)
    failed = False
    real_connect = avatars.connect

    @contextmanager
    def failing_connection(settings):
        nonlocal failed
        with real_connect(settings) as connection:
            yield connection
            if not failed and fault == "commit":
                failed = True
                raise psycopg.OperationalError("private database details")
        if not failed and fault == "lost-commit-response":
            failed = True
            raise psycopg.OperationalError("private commit response lost")

    def fail_write(fd):
        raise OSError("private disk details")

    if fault == "write":
        monkeypatch.setattr(avatars.os, "fsync", fail_write)
    else:
        monkeypatch.setattr(avatars, "connect", failing_connection)
    response = upload(client, token, new)
    assert response.status_code == 503 and "private" not in response.text
    current = user(settings, email)
    expected = new if fault == "lost-commit-response" else old
    assert read(client, token).content == expected
    assert (root / str(current["id"]) / current["avatar_key"]).read_bytes() == expected
    assert len(list((root / str(current["id"])).iterdir())) == 1
    if fault != "lost-commit-response":
        assert current == before


@pytest.mark.postgres
def test_parallel_replacement_serializes_files_and_removes_unused_candidates(
    avatar_api, monkeypatch
):
    client, settings, email, token, _, prefix, root = avatar_api
    assert upload(client, token).status_code == 200
    entered, release = Event(), Event()
    original = avatars.os.fsync
    first_write = True

    def gated_write(fd):
        nonlocal first_write
        original(fd)
        if first_write:
            first_write = False
            entered.set()
            assert release.wait(10)

    monkeypatch.setattr(avatars.os, "fsync", gated_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(upload, client, token, picture(color="green"))
        try:
            assert entered.wait(5)
            second = pool.submit(upload, client, token, picture(color="blue"))
            wait_for_account_lock(settings, prefix)
        finally:
            release.set()
        assert first.result(timeout=10).status_code == second.result(timeout=10).status_code == 200
    current = user(settings, email)
    assert read(client, token).content == picture(color="blue")
    assert [p.name for p in (root / str(current["id"])).iterdir()] == [current["avatar_key"]]


@pytest.mark.postgres
def test_deferred_cleanup_retries_without_deleting_current_avatar(avatar_api, monkeypatch):
    from pathlib import Path

    client, settings, email, token, _, _, root = avatar_api
    assert upload(client, token).status_code == 200
    original = Path.unlink

    def unavailable(*args, **kwargs):
        raise OSError("private storage details")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", unavailable)
        assert upload(client, token, picture(color="blue")).status_code == 200
    current = user(settings, email)
    directory = root / str(current["id"])
    assert len(list(directory.iterdir())) == 2
    assert read(client, token).content == picture(color="blue")
    assert Path.unlink is original
    assert upload(client, token, picture(color="green")).status_code == 200
    current = user(settings, email)
    assert [p.name for p in directory.iterdir()] == [current["avatar_key"]]
