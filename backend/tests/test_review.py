import json
from dataclasses import replace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from test_password_reset import login
from test_password_reset import reset_api as reset_api

from studyloop.content_import import build_bundle, publish_bundle, validate_bundle
from studyloop.main import create_app
from studyloop.registration import connect
from studyloop.settings import Settings


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "sample.pdf"
    with pymupdf.open() as pdf:
        first = pdf.new_page()
        for y, text in [
            (90, "1. Chapter"),
            (130, "Parent introduction."),
            (180, "1.1 Container"),
            (220, "1.1.1 Section"),
            (260, "1.1.1.1 First"),
            (300, "First paragraph."),
        ]:
            first.insert_text((75, y), text)
        for x in (75, 275, 475):
            first.draw_line((x, 360), (x, 460))
        for y in (360, 410, 460):
            first.draw_line((75, y), (475, y))
        first.insert_text((90, 390), "A")
        first.insert_text((290, 390), "B")
        first.insert_text((90, 440), "C")
        first.insert_text((290, 440), "D")
        second = pdf.new_page()
        second.insert_text((75, 90), "Continued example on another page.")
        second.insert_text((75, 180), "1.1.1.2 Second")
        second.insert_text((75, 230), "Second paragraph.")
        pdf.set_toc(
            [
                [1, "1. Chapter", 1, 72],
                [2, "1.1 Container", 1, 165],
                [3, "1.1.1 Section", 1, 205],
                [4, "1.1.1.1 First", 1, 245],
                [4, "1.1.1.2 Second", 2, 165],
            ]
        )
        pdf.save(source)
    directory = tmp_path / "bundle"
    build_bundle(source, directory, 1, 2, "Test material")
    return directory


def test_pdf_headings_figures_cross_page_and_stable_ids(bundle, tmp_path):
    manifest = validate_bundle(bundle)
    points = manifest["points"]
    assert len(manifest["toc"]) == 5 and len(points) == 3
    assert points[0]["blocks"][0]["text"] == "Parent introduction."
    assert points[1]["source_start"] == 1 and points[1]["source_end"] == 2
    assert any(b["type"] == "figure" for b in points[1]["blocks"])
    assert any("Continued example" in b.get("text", "") for b in points[1]["blocks"])
    assert points[0]["previous_id"] is None and points[-1]["next_id"] is None
    repeat = build_bundle(bundle / "source.pdf", tmp_path / "again", 1, 2, "Test material")
    assert manifest == repeat
    coverage = json.loads((bundle / "coverage.json").read_text())
    assert {row["kind"] for row in coverage} >= {"heading", "paragraph", "figure"}


def test_invalid_bundle_fails_before_storage_or_database(bundle, tmp_path):
    manifest = validate_bundle(bundle)
    name = next(iter(manifest["pages"].values()))
    (bundle / name).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="fingerprint"):
        publish_bundle(bundle, Settings(review_directory=str(tmp_path / "private")))
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize(
    "suffix",
    [
        "/books",
        "/books/book/toc",
        "/points/point",
        "/books/book/assets/file.jpg",
        "/books/book/source",
        "/books/book/source/pages/1",
    ],
)
def test_all_review_routes_require_authentication(suffix):
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/review" + suffix)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.postgres
def test_real_import_reimport_persistence_and_revocation(reset_api, bundle, tmp_path):
    client, app, settings, _, _, email, _, _ = reset_api
    settings = replace(settings, review_directory=str(tmp_path / "private"))
    app.state.settings = settings
    book = publish_bundle(bundle, settings)
    try:
        publish_bundle(bundle, settings)
        token = login(client, email).json()["token"]
        headers = {"Authorization": "Bearer " + token}
        prefix = "/api/v1/review"
        listing = client.get(prefix + "/books", headers=headers)
        assert book in listing.json()["items"]
        toc = client.get(prefix + f"/books/{book['id']}/toc", headers=headers).json()
        points = [n["point_id"] for n in toc["items"] if n["point_id"]]
        assert len(points) == 3
        assert (
            client.get(prefix + "/points/" + points[1], headers=headers).json()["source_end"] == 2
        )
        paths = [f"/books/{book['id']}/source", f"/books/{book['id']}/source/pages/1"]
        for path in paths:
            response = client.get(prefix + path, headers=headers)
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        # New app/connection still resolves the imported content and private files.
        with TestClient(create_app(settings)) as restarted:
            assert (
                restarted.get(prefix + "/points/" + points[0], headers=headers).status_code == 200
            )
        with connect(settings) as connection:
            connection.execute("UPDATE users SET enabled=false WHERE email=%s", (email,))
        for path in ["/books", "/points/" + points[0], *paths]:
            assert client.get(prefix + path, headers=headers).status_code == 401
    finally:
        with connect(settings) as connection:
            connection.execute("DELETE FROM review_points WHERE book_id=%s", (book["id"],))
            connection.execute("DELETE FROM review_books WHERE id=%s", (book["id"],))
