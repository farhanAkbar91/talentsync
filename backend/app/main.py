"""Application factory FastAPI — TalentSync AI."""

import logging
import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.context import request_id_ctx
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import build_engine

logger = logging.getLogger(__name__)


def _warm_embedding_model(settings: Settings) -> None:
    """Pre-load model embedding (M3) — request pertama tidak lagi membayar
    cold-start ±30 dtk torch (terverifikasi di E2E Wave 3).

    Mode sinkron (embedding_prewarm_sync=True, dipakai E2E): memblokir startup
    sehingga model pasti siap sebelum test pertama — deterministic. Mode latar
    (produksi): thread daemon; get_embedder kini ber-lock sehingga tidak ada
    double-load bila request datang saat pemuatan berjalan. Gagal warm-up
    tidak fatal: embed on-the-fly tetap berjalan saat dibutuhkan."""

    def _load() -> None:
        try:
            from app.ai.matching.embedder import get_embedder

            embedder = get_embedder(settings.embedding_model)
            # Warm-up INFERENSI pertama: torch lazy-init ±30 dtk terjadi di sini,
            # bukan pada request pengguna (muat model saja belum cukup — Wave 3).
            embedder.encode(["pre-warm"])
            logger.info("Model embedding siap (pre-warm + inferensi): %s", settings.embedding_model)
        except Exception as exc:  # pragma: no cover — lingkungan tanpa torch dsb.
            logger.warning("Pre-warm model embedding dilewati: %s", exc)

    if settings.embedding_prewarm_sync:
        _load()
        return
    threading.Thread(target=_load, name="embedder-warmup", daemon=True).start()


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

    if s.embeddings_enabled:
        _warm_embedding_model(s)

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"app": s.app_name, "version": APP_VERSION, "docs": "/docs"}

    return app


app = create_app()
