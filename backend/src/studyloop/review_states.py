"""Private, explicitly changed review state and ordered account lists."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from studyloop.registration import AuthError, connect
from studyloop.review import PRIVATE, missing
from studyloop.sessions import current_user, lock_current_user

router = APIRouter(prefix="/api/v1/me/review")
Mastery = Literal["unlearned", "needs_review", "mastered"]


class StateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    bookmarked: StrictBool | None = None
    mastery: Mastery | None = None
    expected_revision: int = Field(ge=0, le=9007199254740991, strict=True)
    operation_id: UUID

    @model_validator(mode="after")
    def explicit_changes(self):
        fields = self.model_fields_set & {"bookmarked", "mastery"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("请明确选择收藏或掌握程度")
        return self


def state_row(connection, user_id, point_id):
    row = connection.execute(
        "SELECT point_id,bookmarked,mastery,revision FROM review_states "
        "WHERE user_id=%s AND point_id=%s",
        (user_id, point_id),
    ).fetchone()
    return row or {"point_id": point_id, "bookmarked": False, "mastery": "unlearned", "revision": 0}


def check_point(connection, point_id):
    if not connection.execute("SELECT 1 FROM review_points WHERE id=%s", (point_id,)).fetchone():
        missing()


@router.get("/points/{point_id}/state")
def get_state(point_id: str, request: Request, user: Annotated[dict, Depends(current_user)]):
    with connect(request.app.state.settings) as connection:
        check_point(connection, point_id)
        state = state_row(connection, user["id"], point_id)
    return JSONResponse(state, headers=PRIVATE)


@router.patch("/points/{point_id}/state")
def patch_state(
    point_id: str, body: StateInput, request: Request, user: Annotated[dict, Depends(current_user)]
):
    payload = body.model_dump(mode="json", exclude_unset=True)
    with connect(request.app.state.settings) as connection:
        lock_current_user(connection, user)
        check_point(connection, point_id)
        replay = connection.execute(
            "SELECT request,response FROM review_state_operations "
            "WHERE user_id=%s AND point_id=%s AND operation_id=%s",
            (user["id"], point_id, body.operation_id),
        ).fetchone()
        if replay:
            if replay["request"] != payload:
                raise AuthError(409, "REVIEW_OPERATION_REUSED", "保存标识已使用，请刷新当前状态。")
            return JSONResponse(replay["response"], headers=PRIVATE)
        previous = state_row(connection, user["id"], point_id)
        if body.expected_revision != previous["revision"]:
            raise AuthError(409, "REVIEW_STATE_CONFLICT", "其他设备已更新状态，请刷新后重新选择。")
        state = {**previous, "revision": previous["revision"] + 1}
        for field in body.model_fields_set & {"bookmarked", "mastery"}:
            state[field] = getattr(body, field)
        connection.execute(
            "INSERT INTO review_states(user_id,point_id,bookmarked,mastery,revision) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(user_id,point_id) DO UPDATE SET "
            "bookmarked=excluded.bookmarked,mastery=excluded.mastery,revision=excluded.revision",
            (user["id"], point_id, state["bookmarked"], state["mastery"], state["revision"]),
        )
        connection.execute(
            "INSERT INTO review_state_operations(user_id,point_id,operation_id,request,response) "
            "VALUES (%s,%s,%s,%s,%s)",
            (user["id"], point_id, body.operation_id, Jsonb(payload), Jsonb(state)),
        )
    return JSONResponse(state, headers=PRIVATE)


@router.get("/books/{book_id}/points")
def list_points(
    book_id: str,
    request: Request,
    user: Annotated[dict, Depends(current_user)],
    filter: Literal["bookmarked", "needs_review"],
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
):
    predicate = "s.bookmarked" if filter == "bookmarked" else "s.mastery='needs_review'"
    with connect(request.app.state.settings) as connection:
        # Count and rows use one snapshot, even if another device edits membership.
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if not connection.execute("SELECT 1 FROM review_books WHERE id=%s", (book_id,)).fetchone():
            missing()
        total = connection.execute(
            "SELECT count(*) AS n FROM review_states s JOIN review_points p ON p.id=s.point_id "
            f"WHERE s.user_id=%s AND p.book_id=%s AND {predicate}",
            (user["id"], book_id),
        ).fetchone()["n"]
        page = min(page, max(1, (total + 19) // 20))
        items = connection.execute(
            "SELECT s.point_id,s.bookmarked,s.mastery,s.revision,p.document->>'title' AS title,"
            "p.document->'path' AS path FROM review_states s "
            "JOIN review_points p ON p.id=s.point_id "
            f"WHERE s.user_id=%s AND p.book_id=%s AND {predicate} "
            "ORDER BY p.ordinal LIMIT 20 OFFSET %s",
            (user["id"], book_id, (page - 1) * 20),
        ).fetchall()
    return JSONResponse(
        {"items": items, "total": total, "page": page, "page_size": 20}, headers=PRIVATE
    )
