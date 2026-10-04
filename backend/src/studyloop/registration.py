import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from argon2 import PasswordHasher
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator

from studyloop.mail import MailUnavailable
from studyloop.settings import Settings

router = APIRouter(prefix="/api/v1/auth")
password_hasher = PasswordHasher()
ACCEPTED = (
    "请求已受理，无法确认邮件是否送达。请检查收件箱及垃圾邮件；若未收到或发送失败，请 60 秒后重试。"
)


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        try:
            return validate_email(
                value.strip().lower(), check_deliverability=False, allow_smtputf8=False
            ).normalized.lower()
        except EmailNotValidError:
            raise ValueError("邮箱格式不正确") from None


class RegisterInput(EmailInput):
    password: str = Field(min_length=12, max_length=128, repr=False)
    nickname: str | None = Field(default=None, max_length=120)

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str | None) -> str:
        value = (value or "").strip() or "学习者"
        if len(value) > 30:
            raise ValueError("昵称最多 30 个字符")
        return value


class VerifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: str = Field(min_length=1, max_length=128, repr=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def connect(settings: Settings):
    if not settings.database_url:
        raise psycopg.OperationalError()
    return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)


def now() -> datetime:
    return datetime.now(UTC)


def limit(settings: Settings, key: str, maximum: int, seconds: int) -> None:
    current = now()
    # Independent committed transaction: failed requests also count, across workers/restarts.
    with connect(settings) as connection:
        connection.execute("DELETE FROM auth_rate_limits WHERE expires_at <= %s", (current,))
        row = connection.execute(
            """INSERT INTO auth_rate_limits (key, attempts, expires_at) VALUES (%s, 1, %s)
               ON CONFLICT (key) DO UPDATE SET attempts = auth_rate_limits.attempts + 1
               RETURNING attempts""",
            (digest(key), current + timedelta(seconds=seconds)),
        ).fetchone()
    if row["attempts"] > maximum:
        raise AuthError(429, "RATE_LIMITED", "请求过于频繁，请稍后重试。")


def entry_limit(request: Request, endpoint: str, maximum: int):
    # Only the trusted loopback reverse proxy may supply forwarded client addresses.
    ip = request.client.host if request.client else "unknown"
    limit(request.app.state.settings, f"{endpoint}:{ip}", maximum, 600)


def deliver(connection, user, settings: Settings, sender) -> None:
    token = secrets.token_urlsafe(32)
    link = f"{settings.pages_url}#/verify-email?token={token}"
    sender(settings, user["email"], link)
    current = now()
    # Caller holds the account lock throughout send + replacement. Failed send writes nothing.
    connection.execute(
        """INSERT INTO email_tokens (user_id, purpose, digest, expires_at)
           VALUES (%s, 'verify_email', %s, %s)
           ON CONFLICT (user_id, purpose) DO UPDATE SET digest = EXCLUDED.digest,
               expires_at = EXCLUDED.expires_at, consumed_at = NULL""",
        (user["id"], digest(token), current + timedelta(hours=24)),
    )
    connection.execute(
        "UPDATE users SET verification_sent_at = %s WHERE id = %s", (current, user["id"])
    )


def reply(code: str, message: str, status: int = 200):
    return JSONResponse(
        {"code": code, "message": message},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/register")
def register(body: RegisterInput, request: Request):
    settings = request.app.state.settings
    entry_limit(request, "register", settings.register_limit)
    password_hash = password_hasher.hash(body.password)
    with connect(settings) as connection:
        user = connection.execute(
            """INSERT INTO users (id, email, password_hash, nickname)
               VALUES (%s, %s, %s, %s) ON CONFLICT (email) DO NOTHING RETURNING id""",
            (uuid4(), body.email, password_hash, body.nickname or "学习者"),
        ).fetchone()
    if user is None:
        raise AuthError(409, "ACCOUNT_EXISTS", "该邮箱已注册；尚未验证时，请使用重发验证邮件。")
    # Persist pending identity before SMTP, so a transport failure never loses the account.
    with connect(settings) as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE id = %s FOR UPDATE", (user["id"],)
        ).fetchone()
        if not user["email_verified"] and not user["verification_sent_at"]:
            try:
                deliver(connection, user, settings, request.app.state.send_verification)
            except MailUnavailable:
                raise AuthError(
                    503,
                    "MAIL_UNAVAILABLE",
                    "账号已保存，但验证邮件发送失败。请使用重发验证邮件重试。",
                ) from None
    return reply("REGISTERED", "注册成功，请查看邮箱并在 24 小时内验证。验证后仍需单独登录。", 201)


@router.post("/resend-verification")
def resend(body: EmailInput, request: Request):
    settings = request.app.state.settings
    entry_limit(request, "resend", settings.resend_limit)
    # Same cooldown and reply for every email, including missing/verified/disabled accounts.
    limit(settings, f"resend-email:{body.email}", 1, 60)
    with connect(settings) as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE email = %s FOR UPDATE", (body.email,)
        ).fetchone()
        sent_at = user["verification_sent_at"] if user else None
        if (
            user
            and not user["email_verified"]
            and user["enabled"]
            and (sent_at is None or now() - sent_at >= timedelta(seconds=60))
        ):
            try:
                deliver(connection, user, settings, request.app.state.send_verification)
            except MailUnavailable:
                # The response is identical for every address, including SMTP DATA failures.
                # The failed transaction leaves any previous valid token untouched.
                pass
    return reply("VERIFICATION_REQUEST_ACCEPTED", ACCEPTED, 202)


@router.post("/verify-email")
def verify(body: VerifyInput, request: Request):
    settings = request.app.state.settings
    token_digest = digest(body.token)
    with connect(settings) as connection:
        token = connection.execute(
            "SELECT user_id FROM email_tokens WHERE digest = %s AND purpose = 'verify_email'",
            (token_digest,),
        ).fetchone()
        if token:
            # Same lock order as resend; recheck token after waiting for concurrent replacement.
            connection.execute(
                "SELECT id FROM users WHERE id = %s FOR UPDATE", (token["user_id"],)
            ).fetchone()
            consumed = connection.execute(
                """UPDATE email_tokens SET consumed_at = %s
                   WHERE digest = %s AND purpose = 'verify_email'
                     AND consumed_at IS NULL AND expires_at > %s RETURNING user_id""",
                (now(), token_digest, now()),
            ).fetchone()
            if consumed:
                connection.execute(
                    "UPDATE users SET email_verified = true WHERE id = %s", (consumed["user_id"],)
                )
                return reply("EMAIL_VERIFIED", "邮箱验证成功。请前往登录页面登录。")
    raise AuthError(
        400, "INVALID_VERIFICATION_TOKEN", "验证链接无效、已使用或已过期，请重新申请邮件。"
    )
