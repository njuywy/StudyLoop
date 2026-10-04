import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from studyloop.admin import router as admin_router
from studyloop.avatars import router as avatar_router
from studyloop.database import check_database
from studyloop.mail import send_password_reset, send_verification
from studyloop.passwords import router as password_router
from studyloop.positions import router as positions_router
from studyloop.profile import router as profile_router
from studyloop.registration import AuthError, reply, router
from studyloop.review import router as review_router
from studyloop.sessions import auth_router, me_router
from studyloop.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    application = FastAPI(title="StudyLoop API", version="0.1.0", debug=False)
    application.state.settings = settings
    application.state.send_verification = send_verification
    application.state.send_password_reset = send_password_reset
    application.include_router(router)
    application.include_router(auth_router)
    application.include_router(me_router)
    application.include_router(password_router)
    application.include_router(profile_router)
    application.include_router(avatar_router)
    application.include_router(admin_router)
    application.include_router(review_router)
    application.include_router(positions_router)

    @application.exception_handler(AuthError)
    async def auth_error(request: Request, error: AuthError):
        return reply(error.code, error.message, error.status)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        if "/review/" in request.url.path:
            return reply("INVALID_REVIEW_INPUT", "请检查资料、知识点或阅读位置。", 422)
        # FastAPI's default details echo submitted passwords/tokens; never serialize input.
        return reply(
            "INVALID_INPUT", "请检查邮箱、密码（12～128 个字符）和昵称（最多 30 个字符）。", 422
        )

    @application.exception_handler(psycopg.Error)
    async def database_error(request: Request, error: psycopg.Error):
        return reply("DATABASE_UNAVAILABLE", "平台连接暂不可用，请稍后重试。", 503)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.get("/api/v1/health")
    def health():
        if not check_database(settings.database_url):
            return JSONResponse(
                status_code=503,
                content={
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "平台连接暂不可用，请稍后重试。",
                },
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            content={"status": "ok", "database": "ok"},
            headers={"Cache-Control": "no-store"},
        )

    return application


app = create_app()
