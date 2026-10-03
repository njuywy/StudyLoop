from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from studyloop.database import check_database
from studyloop.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    application = FastAPI(title="StudyLoop API", version="0.1.0", debug=False)
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
