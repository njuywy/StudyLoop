"""Build a review bundle off-line, then atomically publish its database references.

The source and generated assets remain outside Git/Pages. Import never deletes
previous bundles: a failed/ambiguous commit must not remove a live resource.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import pymupdf
from psycopg.types.json import Jsonb

from studyloop.registration import connect
from studyloop.settings import Settings


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", text).replace("（", "(").replace("）", ")")


def identity(version, *parts):
    return fingerprint((version + ":" + ":".join(map(str, parts))).encode())[:32]


def layout_blocks(page):
    blocks = page.get_text("dict")["blocks"]
    if not any(
        "Math" in span["font"]
        for block in blocks
        if block["type"] == 0
        for line in block["lines"]
        for span in line["spans"]
    ):
        return blocks
    # Math font metrics can extend into the header or adjacent paragraphs. Use
    # glyph outlines on these pages; leave previously published ordinary pages
    # at their original coordinates so their anchors do not change.
    previous = pymupdf.TOOLS.unset_quad_corrections()
    try:
        pymupdf.TOOLS.unset_quad_corrections(True)
        return page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT | pymupdf.TEXT_ACCURATE_BBOXES)[
            "blocks"
        ]
    finally:
        pymupdf.TOOLS.unset_quad_corrections(previous)


def page_lines(page):
    result = []
    for block in layout_blocks(page):
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                result.append({"text": text, "bbox": list(line["bbox"]), "dir": line["dir"]})
    return sorted(result, key=lambda line: (round(line["bbox"][1], 1), line["bbox"][0]))


def locate_heading(entry, lines):
    target = compact(entry[1])
    y = entry[3]["to"].y
    candidates = [
        (i, line)
        for i, line in enumerate(lines)
        if abs(line["bbox"][1] - y) < 35 and line["dir"][0] > 0.99
    ]
    for index, line in candidates:
        value = compact(line["text"])
        if value == target:
            return line["bbox"][1], {index}
        if len(value) > 4 and target.startswith(value):
            indices = {index}
            for following in range(index + 1, len(lines)):
                if lines[following]["bbox"][1] - line["bbox"][1] > 100:
                    break
                if lines[following]["dir"][0] < 0.99:
                    continue
                value += compact(lines[following]["text"])
                indices.add(following)
                if value == target:
                    return line["bbox"][1], indices
                if not target.startswith(value):
                    break
    raise ValueError(f"Cannot locate heading at source page {entry[2]}: {entry[1]}")


def figure_regions(page):
    # Multi-column tables retain their original geometry, including embedded symbols.
    regions = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables if t.col_count > 1]
    for image in page.get_image_info():
        rect = pymupdf.Rect(image["bbox"])
        if not any(r.intersects(rect) for r in regions):
            regions.append(rect)
        else:
            for r in regions:
                if r.intersects(rect):
                    r.include_rect(rect)
    # Other vector diagrams: ignore rectangular paragraph borders and underlines.
    paths = [d for d in page.get_drawings() if any(i[0] in {"c", "qu"} for i in d["items"])]
    if paths:
        for rect in page.cluster_drawings():
            if any(rect.intersects(d["rect"]) for d in paths):
                if not any(r.intersects(rect) for r in regions):
                    regions.append(rect)
    # Code is positioned with font/coordinates rather than literal indentation in
    # this PDF. Preserve each contiguous code excerpt as a zoomable local image.
    code_lines, math_lines = [], []
    blocks = layout_blocks(page)
    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            if any("Courier" in span["font"] for span in line["spans"]):
                code_lines.append(pymupdf.Rect(line["bbox"]))
            if any("Math" in span["font"] for span in line["spans"]):
                math_lines.append(pymupdf.Rect(line["bbox"]))
    if math_lines:
        # On math pages, some fractions use only ordinary fonts. A short bar
        # with nearby numerator AND denominator distinguishes these from rules
        # and underlines. Include the adjacent equation text on the same row.
        lines = [line for b in blocks if b["type"] == 0 for line in b["lines"]]
        spans = [
            pymupdf.Rect(s["bbox"]) for line in lines for s in line["spans"] if s["text"].strip()
        ]
        for drawing in page.get_drawings():
            for item in drawing["items"]:
                if item[0] != "l":
                    continue
                a, b = item[1:]
                if abs(a.y - b.y) > 0.1 or not 3 <= abs(a.x - b.x) <= 150:
                    continue
                left, right = sorted((a.x, b.x))
                aligned = [r for r in spans if left - 2 <= (r.x0 + r.x1) / 2 <= right + 2]
                above = [r for r in aligned if 0 <= a.y - r.y1 <= 8]
                below = [r for r in aligned if 0 <= r.y0 - a.y <= 8]
                if not above or not below:
                    continue
                fraction = pymupdf.Rect(left, a.y - 0.01, right, a.y + 0.01)
                for rect in above + below:
                    fraction.include_rect(rect)
                math_lines.append(fraction)
                for line in lines:
                    rect = pymupdf.Rect(line["bbox"])
                    if rect.intersects(fraction + (-12, 0, 12, 0)):
                        math_lines.append(rect)
    excerpts = []
    # Fractions, sums and subscripts need their two-dimensional arrangement.
    # A small vertical gap joins fragments of one formula, not nearby prose.
    for lines, gap in ((code_lines, 18), (math_lines, 8)):
        grouped = []
        for rect in sorted(lines, key=lambda r: r.y0):
            if grouped and rect.y0 - grouped[-1].y1 < gap:
                grouped[-1].include_rect(rect)
            else:
                grouped.append(rect)
        excerpts.extend(grouped)
    for rect in excerpts:
        overlapping = [r for r in regions if r.intersects(rect)]
        for existing in overlapping:
            rect.include_rect(existing)
            regions.remove(existing)
        regions.append(rect)
    # Some table cells have glyphs protruding past the drawn border. A line
    # assigned to a crop must fit in the image, including that overhang.
    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text_rect = pymupdf.Rect(line["bbox"])
            for rect in regions:
                if (
                    rect.intersects(text_rect)
                    and rect.contains(text_rect.tl + (2, 2))
                    and not (rect + (-2, -2, 2, 2)).contains(text_rect)
                ):
                    rect.include_rect(text_rect)
    regions = [
        r
        for i, r in enumerate(regions)
        if not any(
            other.contains(r) and (other != r or j < i) for j, other in enumerate(regions) if j != i
        )
    ]
    return sorted(regions, key=lambda r: (r.y0, r.x0))


def raster(page, rect, directory):
    rect = (rect + (-2, -2, 2, 2)) & page.rect
    data = page.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=rect, alpha=False).tobytes(
        "jpeg", jpg_quality=92
    )
    name = fingerprint(data) + ".jpg"
    (directory / name).write_bytes(data)
    return name, round(rect.width * 2.5), round(rect.height * 2.5)


def join_wrapped_lines(blocks):
    """Join full-width PDF line wraps, retaining indented paragraph boundaries."""
    result = []
    for block in blocks:
        previous = result[-1] if result else None
        if (
            previous
            and previous["type"] == block["type"] == "paragraph"
            and previous["page"] == block["page"]
            and block["bbox"][0] < 70
            and previous["bbox"][2] >= 500
            and 0 < block["bbox"][1] - previous["bbox"][3] < 25
        ):
            separator = " " if previous["text"][-1].isascii() and block["text"][0].isascii() else ""
            previous["text"] += separator + block["text"]
            previous["bbox"][2:] = block["bbox"][2:]
        else:
            result.append(block)
    return result


def build_bundle(source, output, start_page, end_page, title, *, stop_before=None, margin_top=65):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError("Output must be a new private directory")
    output.mkdir(parents=True, mode=0o700)
    try:
        version = fingerprint(source.read_bytes())
        book_id = version[:32]
        with pymupdf.open(source) as pdf:
            if (
                pdf.is_encrypted
                or not 1 <= start_page <= end_page <= len(pdf)
                or not 0 <= margin_top <= 100
            ):
                raise ValueError("Invalid source or page range")
            entries = [e for e in pdf.get_toc(False) if start_page <= e[2] <= end_page]
            if not entries:
                raise ValueError("No chapter bookmarks in selected pages")
            lines_by_page = {n: page_lines(pdf[n - 1]) for n in range(start_page, end_page + 1)}
            boundary = None
            if stop_before:
                matches = [i for i, e in enumerate(entries) if e[1] == stop_before]
                if len(matches) != 1 or matches[0] == 0:
                    raise ValueError("Stop heading must uniquely follow selected content")
                index = matches[0]
                entry = entries[index]
                y, _ = locate_heading(entry, lines_by_page[entry[2]])
                boundary = (entry[2], y)
                entries = entries[:index]
                lines_by_page = {n: lines for n, lines in lines_by_page.items() if n <= entry[2]}
            nodes, heading_lines, stack = [], {}, []
            for entry in entries:
                level, heading, number = entry[:3]
                y, matched = locate_heading(entry, lines_by_page[number])
                heading_lines.setdefault(number, set()).update(matched)
                node_id = identity(version, "heading", number, round(y, 2))
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                node = {
                    "id": node_id,
                    "title": heading,
                    "level": level,
                    "parent_id": stack[-1]["id"] if stack else None,
                    "page": number,
                    "y": round(y, 2),
                    "point_id": None,
                    "path": [n["title"] for n in stack] + [heading],
                }
                nodes.append(node)
                stack.append(node)
            if [(n["page"], n["y"]) for n in nodes] != sorted((n["page"], n["y"]) for n in nodes):
                raise ValueError("Bookmark order disagrees with source layout")
            points = {
                n["id"]: {
                    "id": n["id"],
                    "book_id": book_id,
                    "version": version,
                    "title": n["title"],
                    "path": n["path"],
                    "blocks": [],
                    "source_start": n["page"],
                    "source_end": n["page"],
                }
                for n in nodes
            }
            coverage, pages, current = [], {}, 0
            for number, lines in lines_by_page.items():
                page = pdf[number - 1]
                pages[str(number)] = raster(page, page.rect, output)[0]
                regions = figure_regions(page)
                if boundary and number == boundary[0]:
                    if any(r.y0 < boundary[1] < r.y1 for r in regions):
                        raise ValueError("A figure crosses the selected chapter boundary")
                    regions = [r for r in regions if r.y0 < boundary[1]]
                pieces = []
                for i, line in enumerate(lines):
                    rect = pymupdf.Rect(line["bbox"])
                    in_figure = any(
                        r.intersects(rect) and r.contains(rect.tl + (2, 2)) for r in regions
                    )
                    reason = "paragraph"
                    if boundary and (number, rect.y0) >= boundary:
                        reason = "outside-selection"
                    elif i in heading_lines.get(number, set()):
                        reason = "heading"
                    elif in_figure:
                        reason = "figure"
                    elif line["dir"][0] < 0.99:
                        reason = "rotated-watermark"
                    elif rect.y0 < margin_top or rect.y0 > page.rect.height - 70:
                        reason = "margin"
                    coverage.append(
                        {
                            "page": number,
                            "line": i,
                            "bbox": line["bbox"],
                            "kind": reason,
                            "text": line["text"],
                        }
                    )
                    if reason == "paragraph":
                        pieces.append(
                            {"type": "paragraph", "text": line["text"], "bbox": line["bbox"]}
                        )
                for rect in regions:
                    name, width, height = raster(page, rect, output)
                    pieces.append(
                        {
                            "type": "figure",
                            "asset_id": name,
                            "width": width,
                            "height": height,
                            "alt": f"原文第 {number} 页图表",
                            "bbox": list(rect),
                        }
                    )
                for piece in sorted(pieces, key=lambda b: (b["bbox"][1], b["bbox"][0])):
                    pos = (number, piece["bbox"][1])
                    while (
                        current + 1 < len(nodes)
                        and (nodes[current + 1]["page"], nodes[current + 1]["y"]) <= pos
                    ):
                        current += 1
                    node = nodes[current]
                    if pos < (node["page"], node["y"]):
                        raise ValueError(f"Unassigned content on page {number}")
                    piece["id"] = identity(
                        version, "block", number, *(round(v, 2) for v in piece["bbox"])
                    )
                    piece["page"] = number
                    point = points[node["id"]]
                    point["blocks"].append(piece)
                    point["source_end"] = number
            documents = []
            for node in nodes:
                point = points[node["id"]]
                if point["blocks"]:
                    point["blocks"] = join_wrapped_lines(point["blocks"])
                    node["point_id"] = point["id"]
                    documents.append(point)
                elif not any(n["parent_id"] == node["id"] for n in nodes):
                    raise ValueError(f"Empty leaf knowledge point: {node['title']}")
            for i, point in enumerate(documents):
                point["previous_id"] = documents[i - 1]["id"] if i else None
                point["next_id"] = documents[i + 1]["id"] if i + 1 < len(documents) else None
            metadata = {
                "id": book_id,
                "title": title,
                "version": version,
                "page_count": len(pdf),
                "point_count": len(documents),
                "coverage_label": f"已上线原文第 {start_page}–{end_page} 页（部分章节）",
            }
            if boundary:
                metadata["coverage_label"] = (
                    f"已上线原文第 {start_page}–{boundary[0]} 页，"
                    f"至「{stop_before}」之前（部分章节）"
                )
            body_entries = pdf.get_toc()[1:]
            if body_entries and body_entries[0][1].strip().lower() in {"目录", "contents"}:
                body_entries = body_entries[1:]
            if (
                not boundary
                and body_entries
                and start_page == body_entries[0][2]
                and end_page == len(pdf)
                and [e[:3] for e in entries] == body_entries
            ):
                metadata["coverage_label"] = "全书内容已收录"
            manifest = {"book": metadata, "toc": nodes, "points": documents, "pages": pages}
        shutil.copyfile(source, output / "source.pdf")
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        (output / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False))
        return manifest
    except Exception:
        shutil.rmtree(output)
        raise


def validate_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    book = manifest["book"]
    if fingerprint((directory / "source.pdf").read_bytes()) != book["version"]:
        raise ValueError("Source fingerprint mismatch")
    if book["id"] != book["version"][:32] or not re.fullmatch(r"[0-9a-f]{64}", book["version"]):
        raise ValueError("Invalid book identity")
    with pymupdf.open(directory / "source.pdf") as source:
        page_count = len(source)
    documents = manifest["points"]
    pages = manifest["pages"]
    if (
        not documents
        or book["page_count"] != page_count
        or book["point_count"] != len(documents)
        or any(not n.isdecimal() or not 1 <= int(n) <= page_count for n in pages)
    ):
        raise ValueError("Invalid content coverage")
    ids, blocks, assets = set(), set(), set(manifest["pages"].values())
    for index, point in enumerate(documents):
        if (
            point["id"] in ids
            or not re.fullmatch(r"[0-9a-f]{32}", point["id"])
            or point["book_id"] != book["id"]
            or point["version"] != book["version"]
            or not point["blocks"]
        ):
            raise ValueError("Invalid/duplicate point")
        if (
            not 1 <= point["source_start"] <= point["source_end"] <= page_count
            or any(
                str(n) not in pages for n in range(point["source_start"], point["source_end"] + 1)
            )
            or point["previous_id"] != (documents[index - 1]["id"] if index else None)
            or point["next_id"]
            != (documents[index + 1]["id"] if index + 1 < len(documents) else None)
        ):
            raise ValueError("Invalid source range or point navigation")
        ids.add(point["id"])
        for block in point["blocks"]:
            if (
                block["id"] in blocks
                or not re.fullmatch(r"[0-9a-f]{32}", block["id"])
                or not point["source_start"] <= block["page"] <= point["source_end"]
                or block["type"] not in {"paragraph", "figure"}
            ):
                raise ValueError("Invalid/duplicate block anchor or source")
            blocks.add(block["id"])
            if block["type"] == "figure":
                assets.add(block["asset_id"])
    nodes, mapped = {}, []
    for node in manifest["toc"]:
        parent = nodes.get(node["parent_id"])
        if (
            node["id"] in nodes
            or not re.fullmatch(r"[0-9a-f]{32}", node["id"])
            or (node["parent_id"] is not None and not parent)
            or node["level"] != (parent["level"] + 1 if parent else 1)
            or str(node["page"]) not in pages
            or node["path"] != (parent["path"] if parent else []) + [node["title"]]
        ):
            raise ValueError("Invalid table of contents hierarchy")
        nodes[node["id"]] = node
        if node["point_id"] and (node["point_id"] not in ids or node["point_id"] != node["id"]):
            raise ValueError("Unresolved table of contents")
        if node["point_id"]:
            mapped.append(node["point_id"])
    if mapped != [point["id"] for point in documents]:
        raise ValueError("Point order disagrees with table of contents")
    for point in documents:
        node = nodes[point["id"]]
        if any(point[key] != node[key] for key in ("title", "path")) or (
            point["source_start"] != node["page"]
        ):
            raise ValueError("Point source disagrees with table of contents")
    for name in assets:
        if not re.fullmatch(r"[0-9a-f]{64}\.jpg", name):
            raise ValueError("Invalid resource reference")
        if fingerprint((directory / name).read_bytes()) != name[:-4]:
            raise ValueError("Resource fingerprint mismatch")
    return manifest


def publish_bundle(directory, settings):
    directory = Path(directory)
    manifest = validate_bundle(directory)
    book = manifest["book"]
    bundle_id = fingerprint((directory / "manifest.json").read_bytes())
    root = Path(settings.review_directory) / book["id"]
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = root / bundle_id
    if not destination.exists():
        staging = Path(tempfile.mkdtemp(prefix=".import-", dir=root))
        try:
            shutil.copytree(directory, staging, dirs_exist_ok=True)
            for file in staging.iterdir():
                os.chmod(file, 0o600)
                with file.open("rb") as stream:
                    os.fsync(stream.fileno())
            os.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    with connect(settings) as connection:
        # Serialize publication of this book, including concurrent first imports.
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (book["id"],))
        existing = connection.execute(
            "SELECT id, document FROM review_points WHERE book_id = %s", (book["id"],)
        ).fetchall()
        incoming = {point["id"]: point for point in manifest["points"]}
        if {r["id"] for r in existing} - incoming.keys():
            raise ValueError("Import cannot remove published knowledge points")
        for row in existing:
            old = {k: v for k, v in row["document"].items() if k not in {"previous_id", "next_id"}}
            new = {
                k: v for k, v in incoming[row["id"]].items() if k not in {"previous_id", "next_id"}
            }
            if old != new:
                raise ValueError("Import cannot change published content or block anchors")
        connection.execute(
            """INSERT INTO review_books (id, metadata, toc, storage_key, pages)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET
               metadata=EXCLUDED.metadata, toc=EXCLUDED.toc, storage_key=EXCLUDED.storage_key,
               pages=EXCLUDED.pages, updated_at=now()""",
            (
                book["id"],
                Jsonb(book),
                Jsonb(manifest["toc"]),
                book["id"] + "/" + bundle_id,
                Jsonb(manifest["pages"]),
            ),
        )
        # Reordering is allowed when front matter is added, IDs remain stable.
        connection.execute(
            "UPDATE review_points SET ordinal = -ordinal-1 WHERE book_id=%s", (book["id"],)
        )
        for ordinal, point in enumerate(manifest["points"]):
            connection.execute(
                """INSERT INTO review_points (id,book_id,ordinal,document) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET ordinal=EXCLUDED.ordinal,
                   document=EXCLUDED.document""",
                (point["id"], book["id"], ordinal, Jsonb(point)),
            )
    return book


def main():
    parser = argparse.ArgumentParser(
        description="Build, validate or publish private review material"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("source")
    build.add_argument("output")
    build.add_argument("--start-page", type=int, required=True)
    build.add_argument("--end-page", type=int, required=True)
    build.add_argument("--title", required=True)
    build.add_argument("--stop-before", help="Stop before this exact bookmark, including mid-page")
    build.add_argument("--margin-top", type=float, default=65, help="Header cutoff in PDF points")
    for name in ("validate", "publish"):
        commands.add_parser(name).add_argument("directory")
    args = parser.parse_args()
    if args.command == "build":
        book = build_bundle(
            args.source,
            args.output,
            args.start_page,
            args.end_page,
            args.title,
            stop_before=args.stop_before,
            margin_top=args.margin_top,
        )["book"]
    elif args.command == "validate":
        book = validate_bundle(args.directory)["book"]
    else:
        book = publish_bundle(args.directory, Settings.from_env())
    print(json.dumps({"id": book["id"], "point_count": book["point_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
