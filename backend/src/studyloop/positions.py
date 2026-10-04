"""Version-checked, account-scoped reading positions."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from studyloop.registration import AuthError, connect
from studyloop.review import PRIVATE, missing
from studyloop.sessions import current_user, lock_current_user

router = APIRouter(prefix="/api/v1/me/review/books")


class PositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    point_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    block_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    offset: float = Field(ge=0, le=1, allow_inf_nan=False, strict=True)
    content_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0, le=9007199254740991, strict=True)
    operation_id: UUID


def position_row(connection, user_id, book_id):
    row = connection.execute(
        "SELECT position FROM review_positions WHERE user_id=%s AND book_id=%s",
        (user_id, book_id),
    ).fetchone()
    return row["position"] if row else None


@router.get("/{book_id}/position")
def get_position(book_id: str, request: Request, user: Annotated[dict, Depends(current_user)]):
    with connect(request.app.state.settings) as connection:
        if not connection.execute("SELECT 1 FROM review_books WHERE id=%s", (book_id,)).fetchone():
            missing()
        position = position_row(connection, user["id"], book_id)
    return JSONResponse({"position": position}, headers=PRIVATE)


@router.put("/{book_id}/position")
def save_position(
    book_id: str,
    body: PositionInput,
    request: Request,
    user: Annotated[dict, Depends(current_user)],
):
    payload = body.model_dump(mode="json")
    with connect(request.app.state.settings) as connection:
        # Account lock serializes first writes as well as existing rows; credential
        # mutations use this same lock. Keep the active session locked to commit.
        lock_current_user(connection, user)
        replay = connection.execute(
            "SELECT request,response FROM review_position_operations "
            "WHERE user_id=%s AND book_id=%s AND operation_id=%s",
            (user["id"], book_id, body.operation_id),
        ).fetchone()
        if replay:
            if replay["request"] != payload:
                raise AuthError(409, "REVIEW_OPERATION_REUSED", "保存标识已使用，请重新读取位置。")
            return JSONResponse({"position": replay["response"]}, headers=PRIVATE)
        point = connection.execute(
            "SELECT document FROM review_points WHERE id=%s AND book_id=%s FOR SHARE",
            (body.point_id, book_id),
        ).fetchone()
        if not point:
            missing()
        document = point["document"]
        if body.content_version != document["version"] or not any(
            b["id"] == body.block_id for b in document["blocks"]
        ):
            raise AuthError(422, "INVALID_REVIEW_POSITION", "阅读位置已失效，请重新打开知识点。")
        previous = position_row(connection, user["id"], book_id)
        revision = previous["revision"] if previous else 0
        if revision != body.expected_revision:
            return JSONResponse(
                {
                    "code": "REVIEW_POSITION_CONFLICT",
                    "message": "其他设备已更新阅读位置，请选择保留哪一个。",
                    "position": previous,
                },
                status_code=409,
                headers=PRIVATE,
            )
        position = {
            "point_id": body.point_id,
            "block_id": body.block_id,
            "offset": body.offset,
            "content_version": body.content_version,
            "revision": revision + 1,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        connection.execute(
            "INSERT INTO review_positions(user_id,book_id,position) VALUES (%s,%s,%s) "
            "ON CONFLICT(user_id,book_id) DO UPDATE SET position=excluded.position",
            (user["id"], book_id, Jsonb(position)),
        )
        connection.execute(
            "INSERT INTO review_position_operations(user_id,book_id,operation_id,request,response) "
            "VALUES (%s,%s,%s,%s,%s)",
            (user["id"], book_id, body.operation_id, Jsonb(payload), Jsonb(position)),
        )
    return JSONResponse({"position": position}, headers=PRIVATE)
