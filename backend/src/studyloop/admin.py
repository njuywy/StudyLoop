from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool

from studyloop.registration import AuthError, connect
from studyloop.sessions import current_user, lock_current_user

router = APIRouter(prefix="/api/v1/admin/users")
FIELDS = "id, email, nickname, role, email_verified, enabled, created_at"


def require_admin(user):
    if user["role"] != "admin":
        raise AuthError(403, "ADMIN_REQUIRED", "仅管理员可以访问用户管理。")


class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    enabled: StrictBool


@router.get("")
def list_users(
    request: Request,
    user: Annotated[dict, Depends(current_user)],
    page: Annotated[int, Query(ge=1, le=2_147_483_647)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    require_admin(user)
    with connect(request.app.state.settings) as connection:
        require_admin(lock_current_user(connection, user))
        # Both the count and rows use one statement snapshot, including empty pages.
        result = connection.execute(
            "SELECT (SELECT count(*) FROM users) AS total, "
            "COALESCE((SELECT json_agg(p ORDER BY p.created_at, p.id) FROM "
            f"(SELECT {FIELDS} FROM users ORDER BY created_at, id LIMIT %s OFFSET %s) p), "
            "'[]'::json) AS items",
            (page_size, (page - 1) * page_size),
        ).fetchone()
    return JSONResponse(
        {**result, "page": page, "page_size": page_size}, headers={"Cache-Control": "no-store"}
    )


@router.patch("/{user_id}/status")
def set_status(
    user_id: UUID,
    body: StatusInput,
    request: Request,
    user: Annotated[dict, Depends(current_user)],
):
    require_admin(user)
    with connect(request.app.state.settings) as connection:
        # Consistent lock order also handles two admins targeting each other (both rejected).
        connection.execute(
            "SELECT id FROM users WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            ([user["id"], user_id],),
        ).fetchall()
        require_admin(lock_current_user(connection, user))
        target = connection.execute("SELECT role FROM users WHERE id = %s", (user_id,)).fetchone()
        if target is None:
            raise AuthError(404, "USER_NOT_FOUND", "用户不存在，请刷新列表。")
        if target["role"] != "user":
            raise AuthError(400, "ADMIN_STATUS_PROTECTED", "不能修改管理员的启用状态。")
        # 0003's trigger revokes all sessions in this same transaction on disable.
        updated = connection.execute(
            f"UPDATE users SET enabled = %s WHERE id = %s RETURNING {FIELDS}",
            (body.enabled, user_id),
        ).fetchone()
    return JSONResponse(jsonable_encoder(updated), headers={"Cache-Control": "no-store"})
