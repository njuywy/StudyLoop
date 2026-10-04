from typing import Annotated

from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from studyloop.passwords import replace_password_and_revoke
from studyloop.registration import AuthError, connect, password_hasher, reply
from studyloop.sessions import current_user, lock_current_user, user_profile

router = APIRouter(prefix="/api/v1/me")


class NicknameInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    nickname: str

    @field_validator("nickname")
    @classmethod
    def trimmed_nickname(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 30:
            raise ValueError("昵称需要 1～30 个字符")
        return value


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    old_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=12, max_length=128, repr=False)


@router.patch("")
def update_profile(
    body: NicknameInput, request: Request, user: Annotated[dict, Depends(current_user)]
):
    with connect(request.app.state.settings) as connection:
        locked = lock_current_user(connection, user)
        updated = connection.execute(
            "UPDATE users SET nickname = %s WHERE id = %s RETURNING id, email, nickname, role",
            (body.nickname, locked["id"]),
        ).fetchone()
    return JSONResponse(user_profile(updated), headers={"Cache-Control": "no-store"})


@router.post("/change-password")
def change_password(
    body: PasswordInput, request: Request, user: Annotated[dict, Depends(current_user)]
):
    with connect(request.app.state.settings) as connection:
        locked = lock_current_user(connection, user)
        try:
            password_hasher.verify(locked["password_hash"], body.old_password)
        except (VerifyMismatchError, VerificationError):
            raise AuthError(400, "INVALID_CURRENT_PASSWORD", "旧密码不正确，请重试。") from None
        replace_password_and_revoke(
            connection, locked["id"], password_hasher.hash(body.new_password)
        )
    return reply("PASSWORD_CHANGED", "密码已更新，请使用新密码重新登录。")
