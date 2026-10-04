import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from studyloop.mail import MailUnavailable
from studyloop.registration import (
    AuthError,
    EmailInput,
    connect,
    digest,
    entry_limit,
    password_hasher,
    reply,
)

router = APIRouter(prefix="/api/v1/auth")
ACCEPTED = (
    "请求已受理，无法确认邮件是否送达。若邮箱已验证且账号可用，请检查收件箱和垃圾邮件；"
    "重置链接 30 分钟内有效。未收到或发送失败时可稍后重试。"
)


class ResetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=12, max_length=128, repr=False)


def now() -> datetime:
    return datetime.now(UTC)


def replace_password_and_revoke(connection, user_id, password_hash: str) -> None:
    """Caller must hold the users row lock; all writes belong to its transaction."""
    current = now()
    connection.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id)
    )
    connection.execute(
        "UPDATE auth_sessions SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL",
        (current, user_id),
    )
    connection.execute(
        "UPDATE email_tokens SET consumed_at = %s "
        "WHERE user_id = %s AND purpose = 'reset_password' AND consumed_at IS NULL",
        (current, user_id),
    )


@router.post("/request-password-reset")
def request_reset(body: EmailInput, request: Request):
    settings = request.app.state.settings
    entry_limit(request, "password-reset", settings.password_reset_limit)
    with connect(settings) as connection:
        # Serialize mail replacement and consumption through the same account lock.
        user = connection.execute(
            "SELECT id, email, email_verified, enabled FROM users WHERE email = %s FOR UPDATE",
            (body.email,),
        ).fetchone()
        if user and user["email_verified"] and user["enabled"]:
            raw_token = secrets.token_urlsafe(32)
            link = f"{settings.pages_url}#/reset-password?token={raw_token}"
            try:
                request.app.state.send_password_reset(settings, user["email"], link)
            except MailUnavailable:
                # Keep both the response and the previous valid link unchanged on SMTP failure.
                pass
            else:
                connection.execute(
                    """INSERT INTO email_tokens (user_id, purpose, digest, expires_at)
                       VALUES (%s, 'reset_password', %s, %s)
                       ON CONFLICT (user_id, purpose) DO UPDATE SET digest = EXCLUDED.digest,
                           expires_at = EXCLUDED.expires_at, consumed_at = NULL""",
                    (user["id"], digest(raw_token), now() + timedelta(minutes=30)),
                )
    return reply("PASSWORD_RESET_REQUEST_ACCEPTED", ACCEPTED, 202)


@router.post("/reset-password")
def reset_password(body: ResetInput, request: Request):
    token_digest = digest(body.token)
    with connect(request.app.state.settings) as connection:
        token = connection.execute(
            "SELECT user_id FROM email_tokens WHERE digest = %s AND purpose = 'reset_password'",
            (token_digest,),
        ).fetchone()
        if token:
            user = connection.execute(
                "SELECT id, email_verified, enabled FROM users WHERE id = %s FOR UPDATE",
                (token["user_id"],),
            ).fetchone()
            if user and user["email_verified"] and user["enabled"]:
                current = now()
                consumed = connection.execute(
                    """UPDATE email_tokens SET consumed_at = %s
                       WHERE digest = %s AND purpose = 'reset_password'
                         AND consumed_at IS NULL AND expires_at > %s RETURNING user_id""",
                    (current, token_digest, current),
                ).fetchone()
                if consumed:
                    replace_password_and_revoke(
                        connection, user["id"], password_hasher.hash(body.new_password)
                    )
                    return reply("PASSWORD_RESET", "密码已更新，所有旧登录会话已失效。请重新登录。")
    raise AuthError(
        400, "INVALID_RESET_TOKEN", "重置链接无效、已使用或已过期，请重新申请找回密码。"
    )
