import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from studyloop.registration import (
    AuthError,
    EmailInput,
    connect,
    digest,
    entry_limit,
    password_hasher,
    reply,
)

auth_router = APIRouter(prefix="/api/v1/auth")
me_router = APIRouter(prefix="/api/v1")


class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=128, repr=False)


def now() -> datetime:
    return datetime.now(UTC)


def user_profile(user):
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "nickname": user["nickname"],
        "role": user["role"],
    }


def unauthorized():
    raise AuthError(401, "UNAUTHORIZED", "登录状态无效或已过期，请重新登录。")


def current_user(request: Request):
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or separator != " " or not token or len(token) > 128:
        unauthorized()
    with connect(request.app.state.settings) as connection:
        row = connection.execute(
            """SELECT u.id, u.email, u.nickname, u.role, s.digest
               FROM auth_sessions s JOIN users u ON u.id = s.user_id
               WHERE s.digest = %s AND s.revoked_at IS NULL AND s.expires_at > %s
                 AND u.email_verified AND u.enabled""",
            (digest(token), now()),
        ).fetchone()
    if not row:
        unauthorized()
    return row


def lock_current_user(connection, authenticated_user):
    """Recheck credentials after taking the account lock used by credential mutations."""
    user = connection.execute(
        "SELECT * FROM users WHERE id = %s FOR UPDATE", (authenticated_user["id"],)
    ).fetchone()
    if not user or not user["email_verified"] or not user["enabled"]:
        unauthorized()
    active = connection.execute(
        "SELECT 1 FROM auth_sessions WHERE digest = %s AND user_id = %s "
        "AND revoked_at IS NULL AND expires_at > %s FOR SHARE",
        (authenticated_user["digest"], user["id"], now()),
    ).fetchone()
    if not active:
        unauthorized()
    return user


@auth_router.post("/login")
def login(body: LoginInput, request: Request):
    settings = request.app.state.settings
    entry_limit(request, "login", settings.login_limit)
    with connect(settings) as connection:
        user = connection.execute(
            "SELECT id, email, nickname, role, password_hash, email_verified, enabled "
            "FROM users WHERE email = %s",
            (body.email,),
        ).fetchone()
    valid_password = False
    if user:
        try:
            valid_password = password_hasher.verify(user["password_hash"], body.password)
        except (VerifyMismatchError, VerificationError):
            pass
    if not user or not valid_password or not user["email_verified"] or not user["enabled"]:
        raise AuthError(401, "INVALID_CREDENTIALS", "邮箱或密码错误，或账号暂不可登录。")
    raw_token = secrets.token_urlsafe(32)
    expires_at = now() + timedelta(hours=12)
    with connect(settings) as connection:
        # Recheck state inside the issuing transaction to close a disable/login race.
        eligible = connection.execute(
            "SELECT id, email, nickname, role, password_hash FROM users WHERE id = %s "
            "AND email_verified AND enabled FOR UPDATE",
            (user["id"],),
        ).fetchone()
        if not eligible or eligible["password_hash"] != user["password_hash"]:
            raise AuthError(401, "INVALID_CREDENTIALS", "邮箱或密码错误，或账号暂不可登录。")
        connection.execute(
            "INSERT INTO auth_sessions (digest, user_id, expires_at) VALUES (%s, %s, %s)",
            (digest(raw_token), eligible["id"], expires_at),
        )
    return JSONResponse(
        {"token": raw_token, "expires_at": expires_at.isoformat(), "user": user_profile(eligible)},
        headers={"Cache-Control": "no-store"},
    )


@auth_router.post("/logout")
def logout(request: Request, user: Annotated[dict, Depends(current_user)]):
    with connect(request.app.state.settings) as connection:
        connection.execute(
            "UPDATE auth_sessions SET revoked_at = %s WHERE digest = %s AND revoked_at IS NULL",
            (now(), user["digest"]),
        )
    return reply("LOGGED_OUT", "已退出登录。")


@me_router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return JSONResponse(user_profile(user), headers={"Cache-Control": "no-store"})
