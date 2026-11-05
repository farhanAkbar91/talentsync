"""Request-scoped context (request ID) yang dibagikan ke logging dan error envelope."""

from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
