"""Error envelope konsisten untuk seluruh API.

Bentuk respons error (sesuai blueprint §4.5):

    { "error": { "code": "...", "message": "...", "details": [...], "request_id": "..." } }

Pesan ke pengguna berbahasa Indonesia; detail teknis internal (termasuk
exception asli) hanya masuk log, tidak pernah ke respons klien.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_ctx
from app.core.exceptions import DomainError

logger = logging.getLogger(__name__)

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "DEPENDENCY_UNAVAILABLE",
}


def error_response(
    status_code: int, message: str, details: list | None = None, code: str | None = None
) -> JSONResponse:
    body = {
        "error": {
            "code": code or _STATUS_CODES.get(status_code, f"HTTP_{status_code}"),
            "message": message,
            "details": details or [],
            "request_id": request_id_ctx.get(),
        }
    }
    return JSONResponse(
        status_code=status_code, content=body, headers={"X-Request-ID": request_id_ctx.get()}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(exc.status_code, exc.message, exc.details, code=exc.code)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return error_response(422, "Payload tidak valid.", details)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return error_response(500, "Terjadi kesalahan internal.")
