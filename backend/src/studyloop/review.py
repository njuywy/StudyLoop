"""Authenticated delivery of imported content; files are never statically served."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from studyloop.registration import AuthError, connect
from studyloop.sessions import current_user

router = APIRouter(prefix="/api/v1/review", dependencies=[Depends(current_user)])
PRIVATE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
ASSET = re.compile(r"[0-9a-f]{64}\.jpg")


def missing():
    raise AuthError(404, "REVIEW_NOT_FOUND", "这份资料或知识点暂不可用，请返回目录。")


def book_row(settings, book_id):
    with connect(settings) as connection:
        row = connection.execute("SELECT * FROM review_books WHERE id = %s", (book_id,)).fetchone()
    if not row:
        missing()
    return row


def private_file(settings, book, name, mime):
    root = Path(settings.review_directory).resolve()
    path = (root / book["storage_key"] / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AuthError(503, "REVIEW_ASSET_UNAVAILABLE", "图片或原文暂不可用，请稍后重试。")
    return FileResponse(path, media_type=mime, headers=PRIVATE)


@router.get("/books")
def books(request: Request):
    with connect(request.app.state.settings) as connection:
        rows = connection.execute("SELECT metadata FROM review_books ORDER BY id").fetchall()
    return JSONResponse({"items": [row["metadata"] for row in rows]}, headers=PRIVATE)


@router.get("/books/{book_id}/toc")
def toc(book_id: str, request: Request):
    book = book_row(request.app.state.settings, book_id)
    return JSONResponse({"book": book["metadata"], "items": book["toc"]}, headers=PRIVATE)


@router.get("/points/{point_id}")
def point(point_id: str, request: Request):
    with connect(request.app.state.settings) as connection:
        row = connection.execute(
            "SELECT document FROM review_points WHERE id = %s", (point_id,)
        ).fetchone()
    if not row:
        missing()
    return JSONResponse(row["document"], headers=PRIVATE)


@router.get("/books/{book_id}/assets/{asset_id}")
def asset(book_id: str, asset_id: str, request: Request):
    if not ASSET.fullmatch(asset_id):
        missing()
    settings = request.app.state.settings
    book = book_row(settings, book_id)
    return private_file(settings, book, asset_id, "image/jpeg")


@router.get("/books/{book_id}/source")
def source(book_id: str, request: Request):
    settings = request.app.state.settings
    return private_file(settings, book_row(settings, book_id), "source.pdf", "application/pdf")


@router.get("/books/{book_id}/source/pages/{page_number}")
def source_page(book_id: str, page_number: int, request: Request):
    settings = request.app.state.settings
    book = book_row(settings, book_id)
    name = book["pages"].get(str(page_number))
    if not name:
        missing()
    return private_file(settings, book, name, "image/jpeg")
