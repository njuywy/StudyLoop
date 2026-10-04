import json
from dataclasses import replace
from pathlib import Path

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
        first.insert_text((472, 390), "B")  # Slightly overhangs the last table border.
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
    with pymupdf.open(bundle / "source.pdf") as source:
        cell = source[0].search_for("B")[0]
        assert any(
            (pymupdf.Rect(b["bbox"]) + (-2, -2, 2, 2)).contains(cell)
            for b in points[1]["blocks"]
            if b["type"] == "figure" and b["page"] == 1
        )
    assert any("Continued example" in b.get("text", "") for b in points[1]["blocks"])
    assert points[0]["previous_id"] is None and points[-1]["next_id"] is None
    repeat = build_bundle(bundle / "source.pdf", tmp_path / "again", 1, 2, "Test material")
    assert manifest == repeat
    coverage = json.loads((bundle / "coverage.json").read_text())
    assert {row["kind"] for row in coverage} >= {"heading", "paragraph", "figure"}


@pytest.fixture
def chapter_bundles(tmp_path):
    source = tmp_path / "chapters.pdf"
    with pymupdf.open() as pdf:
        for heading in ["Cover", "Contents"]:
            pdf.new_page().insert_text((75, 90), heading)
        first = pdf.new_page()
        first.insert_text((75, 90), "First chapter")
        first.insert_text((75, 130), "Parent introduction")
        first.insert_text((75, 200), "First section")
        first.insert_text((75, 240), "Continues to next page")
        last = pdf.new_page()
        last.insert_text((75, 75), "Tail belongs to the first chapter")
        last.insert_text((75, 300), "Second chapter")
        last.insert_text((75, 340), "Only in the second chapter")
        pdf.set_toc(
            [
                [1, "Cover", 1, 75],
                [1, "Contents", 2, 75],
                [1, "First chapter", 3, 75],
                [2, "First section", 3, 185],
                [1, "Second chapter", 4, 285],
            ]
        )
        pdf.save(source)
    build_bundle(
        source, tmp_path / "partial", 3, 4, "Book", stop_before="Second chapter", margin_top=55
    )
    build_bundle(source, tmp_path / "full", 3, 4, "Book", margin_top=55)
    return tmp_path / "partial", tmp_path / "full"


def test_mid_page_chapter_boundary_preserves_tail_and_stable_partial_content(chapter_bundles):
    partial_dir, full_dir = chapter_bundles
    partial, full = validate_bundle(partial_dir), validate_bundle(full_dir)
    assert len(partial["points"]) == 2
    assert partial["points"][-1]["source_end"] == 4
    assert partial["points"][-1]["blocks"][-1]["text"] == "Tail belongs to the first chapter"
    assert "部分章节" in partial["book"]["coverage_label"]
    assert full["book"]["coverage_label"] == "全书内容已收录"
    for old, new in zip(partial["points"], full["points"], strict=False):
        assert old["id"] == new["id"] and old["blocks"] == new["blocks"]
    coverage = json.loads((partial_dir / "coverage.json").read_text())
    assert any(row["kind"] == "outside-selection" for row in coverage)
    with pytest.raises(ValueError, match="uniquely"):
        build_bundle(
            partial_dir / "source.pdf",
            partial_dir.parent / "bad",
            3,
            4,
            "Book",
            stop_before="Missing",
        )
    assert not (partial_dir.parent / "bad").exists()


@pytest.mark.postgres
def test_second_book_import_does_not_reset_existing_content_or_private_records(
    reset_api, bundle, tmp_path
):
    client, app, settings, _, _, email, _, _ = reset_api
    settings = replace(settings, review_directory=str(tmp_path / "private"))
    app.state.settings = settings
    original = validate_bundle(bundle)
    other_source = tmp_path / "other.pdf"
    with pymupdf.open(bundle / "source.pdf") as pdf:
        pdf.set_metadata({"title": "Independent material"})
        pdf.save(other_source)
    other = build_bundle(other_source, tmp_path / "other", 1, 2, "Other material")
    publish_bundle(bundle, settings)
    headers = {"Authorization": "Bearer " + login(client, email).json()["token"]}
    try:
        point = original["points"][0]
        from uuid import uuid4

        state_path = f"/api/v1/me/review/points/{point['id']}/state"
        state = client.patch(
            state_path,
            headers=headers,
            json={
                "bookmarked": True,
                "mastery": "needs_review",
                "expected_revision": 0,
                "operation_id": str(uuid4()),
            },
        )
        assert state.status_code == 200
        location_path = f"/api/v1/me/review/books/{original['book']['id']}/position"
        location = client.put(
            location_path,
            headers=headers,
            json={
                "point_id": point["id"],
                "block_id": point["blocks"][0]["id"],
                "offset": 0.3,
                "content_version": original["book"]["version"],
                "expected_revision": 0,
                "operation_id": str(uuid4()),
            },
        )
        assert location.status_code == 200
        for _ in range(2):
            publish_bundle(tmp_path / "other", settings)
        assert client.get(state_path, headers=headers).json() == state.json()
        assert client.get(location_path, headers=headers).json() == location.json()
        assert client.get(f"/api/v1/review/points/{point['id']}", headers=headers).json() == point
        empty = client.get(
            f"/api/v1/me/review/books/{other['book']['id']}/points?filter=bookmarked",
            headers=headers,
        )
        assert empty.json()["total"] == 0
        assert (
            client.get(
                f"/api/v1/me/review/books/{other['book']['id']}/position", headers=headers
            ).json()["position"]
            is None
        )
    finally:
        with connect(settings) as connection:
            connection.execute(
                "DELETE FROM review_points WHERE book_id IN (%s,%s)",
                (original["book"]["id"], other["book"]["id"]),
            )
            connection.execute(
                "DELETE FROM review_books WHERE id IN (%s,%s)",
                (original["book"]["id"], other["book"]["id"]),
            )


def test_invalid_bundle_fails_before_storage_or_database(bundle, tmp_path):
    manifest = validate_bundle(bundle)
    name = next(iter(manifest["pages"].values()))
    (bundle / name).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="fingerprint"):
        publish_bundle(bundle, Settings(review_directory=str(tmp_path / "private")))
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("broken", ["page", "next", "parent", "block", "order"])
def test_invalid_structure_cannot_touch_published_storage(bundle, tmp_path, broken):
    manifest = validate_bundle(bundle)
    if broken == "page":
        manifest["points"][0]["source_start"] = 999
    elif broken == "next":
        manifest["points"][0]["next_id"] = "missing-point"
    elif broken == "parent":
        manifest["toc"][0]["parent_id"] = "missing-parent"
    elif broken == "block":
        manifest["points"][0]["blocks"][0]["page"] = 999
    else:
        manifest["toc"].reverse()
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    private = tmp_path / "private"
    private.mkdir()
    (private / "existing-resource").write_bytes(b"preserve me")
    with pytest.raises(ValueError):
        publish_bundle(bundle, Settings(review_directory=str(private)))
    assert list(private.iterdir()) == [private / "existing-resource"]
    assert (private / "existing-resource").read_bytes() == b"preserve me"


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
        original = (bundle / "manifest.json").read_text()
        broken = json.loads(original)
        broken["points"][0]["source_end"] = -1
        (bundle / "manifest.json").write_text(json.dumps(broken))
        with pytest.raises(ValueError):
            publish_bundle(bundle, settings)
        (bundle / "manifest.json").write_text(original)
        assert client.get(prefix + f"/books/{book['id']}/toc", headers=headers).json() == toc
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


def test_wrapped_bookmark_ignores_interleaved_rotated_watermark():
    from studyloop.content_import import locate_heading

    lines = [
        {"text": "A wrapped heading", "bbox": [66, 74, 540, 108], "dir": (1, 0)},
        {"text": "watermark", "bbox": [200, 90, 400, 150], "dir": (0.7, -0.7)},
        {"text": "continued", "bbox": [66, 116, 154, 139], "dir": (1, 0)},
    ]
    entry = [1, "A wrapped heading continued", 1, {"to": pymupdf.Point(84, 72)}]
    assert locate_heading(entry, lines) == (74, {0, 2})


def test_code_excerpt_retains_indentation_as_zoomable_region(tmp_path):
    from studyloop.content_import import figure_regions

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((75, 100), "def example():", fontname="cour", fontsize=10)
        page.insert_text((95, 116), "return 42", fontname="cour", fontsize=10)
        page.insert_text((75, 160), "Ordinary explanatory prose", fontsize=12)
        regions = figure_regions(page)
        assert len(regions) == 1
        assert regions[0].x0 <= 75 and regions[0].y0 < 100
        assert regions[0].y1 > 116 and regions[0].y1 < 160


def test_formula_fraction_keeps_geometry_and_surrounding_prose(tmp_path):
    source = tmp_path / "formula.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((75, 90), "Formula chapter")
        page.insert_text((75, 125), "Before the equation.")
        # Rename a base-14 fixture font to exercise math layout without bundling
        # either the private textbook or an external font dependency.
        font = page.insert_font(fontname="tiro")
        pdf.xref_set_key(font, "BaseFont", "/FixtureMath-Regular")
        page.insert_text((190, 155), "R =", fontname="tiro")
        page.insert_text((225, 148), "1")
        page.insert_text((225, 164), "2")
        page.draw_line((220, 153), (235, 153))
        page.insert_text((75, 198), "After the equation.")
        pdf.set_toc([[1, "Formula chapter", 1, 75]])
        pdf.save(source)
    manifest = build_bundle(source, tmp_path / "formula", 1, 1, "Formula")
    blocks = manifest["points"][0]["blocks"]
    assert [b["type"] for b in blocks] == ["paragraph", "figure", "paragraph"]
    assert blocks[0]["text"] == "Before the equation."
    assert blocks[-1]["text"] == "After the equation."
    assert blocks[1]["bbox"][1] < 148 and blocks[1]["bbox"][3] > 163
    assert blocks[1]["bbox"][0] <= 190 and blocks[1]["bbox"][2] >= 235
    assert validate_bundle(tmp_path / "formula") == manifest


@pytest.mark.postgres
def test_expansion_preserves_two_books_two_users_and_failed_publication(
    reset_api, bundle, chapter_bundles, tmp_path, monkeypatch
):
    from contextlib import contextmanager
    from uuid import uuid4

    from studyloop import content_import

    client, app, settings, _, _, email, account, _ = reset_api
    settings = replace(settings, review_directory=str(tmp_path / "private"))
    app.state.settings = settings
    partial_dir, full_dir = chapter_bundles
    partial, full = validate_bundle(partial_dir), validate_bundle(full_dir)
    other = validate_bundle(bundle)
    books = [partial["book"]["id"], other["book"]["id"]]
    headers = [
        {"Authorization": "Bearer " + login(client, address).json()["token"]}
        for address in [email, account("other")]
    ]
    checks = []
    try:
        publish_bundle(bundle, settings)
        publish_bundle(partial_dir, settings)
        for h, mastery in zip(headers, ["needs_review", "mastered"], strict=True):
            for material in [partial, other]:
                point = material["points"][-1]
                state_url = f"/api/v1/me/review/points/{point['id']}/state"
                state = client.patch(
                    state_url,
                    headers=h,
                    json={
                        "bookmarked": True,
                        "mastery": mastery,
                        "expected_revision": 0,
                        "operation_id": str(uuid4()),
                    },
                )
                assert state.status_code == 200
                position_url = f"/api/v1/me/review/books/{material['book']['id']}/position"
                position = client.put(
                    position_url,
                    headers=h,
                    json={
                        "point_id": point["id"],
                        "block_id": point["blocks"][-1]["id"],
                        "offset": 0.4,
                        "content_version": material["book"]["version"],
                        "expected_revision": 0,
                        "operation_id": str(uuid4()),
                    },
                )
                assert position.status_code == 200
                checks.extend([(h, state_url, state.json()), (h, position_url, position.json())])

        def snapshot():
            with connect(settings) as connection:
                return (
                    connection.execute(
                        "SELECT * FROM review_books WHERE id=ANY(%s) ORDER BY id", (books,)
                    ).fetchall(),
                    connection.execute(
                        "SELECT * FROM review_points WHERE book_id=ANY(%s) ORDER BY id", (books,)
                    ).fetchall(),
                )

        baseline = snapshot()
        original = (full_dir / "manifest.json").read_text()
        altered = json.loads(original)
        altered["points"][0]["blocks"][0]["text"] = "Changed published text"
        (full_dir / "manifest.json").write_text(json.dumps(altered))
        with pytest.raises(ValueError, match="published content"):
            publish_bundle(full_dir, settings)
        (full_dir / "manifest.json").write_text(original)
        assert snapshot() == baseline

        @contextmanager
        def fail_after_book_switch(settings):
            with connect(settings) as connection:

                class InterruptedConnection:
                    def execute(self, query, params=None):
                        if "INSERT INTO review_points" in query:
                            raise RuntimeError("controlled publication interruption")
                        return connection.execute(query, params)

                yield InterruptedConnection()

        with monkeypatch.context() as patch:
            patch.setattr(content_import, "connect", fail_after_book_switch)
            with pytest.raises(RuntimeError, match="interruption"):
                publish_bundle(full_dir, settings)
        assert snapshot() == baseline
        for _ in range(2):
            publish_bundle(full_dir, settings)
        expanded = snapshot()
        with pytest.raises(ValueError, match="cannot remove"):
            publish_bundle(partial_dir, settings)
        assert snapshot() == expanded
        for h, path, expected in checks:
            assert client.get(path, headers=h).json() == expected
        for point in [*full["points"], *other["points"]]:
            response = client.get(f"/api/v1/review/points/{point['id']}", headers=headers[0])
            assert response.status_code == 200 and response.json() == point
        for book in baseline[0]:
            assert (Path(settings.review_directory) / book["storage_key"] / "source.pdf").is_file()
    finally:
        with connect(settings) as connection:
            connection.execute("DELETE FROM review_points WHERE book_id=ANY(%s)", (books,))
            connection.execute("DELETE FROM review_books WHERE id=ANY(%s)", (books,))
