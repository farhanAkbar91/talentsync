"""Exception domain — dipetakan ke error envelope oleh core.errors.

Service layer melempar exception ini; router tidak perlu menangani manual.
"""

from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "BAD_REQUEST"
    default_message = "Permintaan tidak valid."

    def __init__(self, message: str | None = None, *, details: list[Any] | None = None) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details or []


class BadRequestError(DomainError):
    pass


class UnauthenticatedError(DomainError):
    status_code = 401
    code = "UNAUTHORIZED"
    default_message = "Autentikasi diperlukan."


class ForbiddenError(DomainError):
    status_code = 403
    code = "FORBIDDEN"
    default_message = "Akses ditolak untuk peran Anda."


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "Data tidak ditemukan."


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"
    default_message = "Data sudah ada."


class PayloadTooLargeError(DomainError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    default_message = "Ukuran berkas melebihi batas."
