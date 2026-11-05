"""Application factory FastAPI — TalentSync AI."""

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.context import request_id_ctx
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import build_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    configure_logging(s.log_level)

    app = FastAPI(title=s.app_name, version=APP_VERSION)
    # Settings & engine terikat ke instance aplikasi (memudahkan pengujian terisolasi).
    app.state.settings = s
    app.state.engine = build_engine(s.database_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    register_error_handlers(app)

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"app": s.app_name, "version": APP_VERSION, "docs": "/docs"}

    return app


app = create_app()
