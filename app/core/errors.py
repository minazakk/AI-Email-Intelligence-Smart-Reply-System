"""Consistent API error envelope and exception types.

Every error response body looks like::

    {"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

DEFAULT_MESSAGES: dict[int, str] = {
    400: "Bad request.",
    401: "Not authenticated.",
    403: "You do not have permission to perform this action.",
    404: "Resource not found.",
    405: "Method not allowed.",
    409: "Conflict with the current state of the resource.",
    413: "Uploaded payload is too large.",
    415: "Unsupported media type.",
    422: "Request validation failed.",
    429: "Too many requests. Please retry later.",
    500: "Internal server error.",
    502: "Upstream AI provider error.",
    503: "Service unavailable.",
}


def error_body(
    code: str,
    message: str,
    *,
    details: Any = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    if request_id:
        payload["request_id"] = request_id
    return {"error": payload}


class AppError(Exception):
    """Base class for errors that map onto a structured API response."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_error"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "unsupported_media_type"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class AIProviderError(AppError):
    """Raised when the configured AI provider cannot produce a valid result.

    A provider failure is never reported as a successful analysis.
    """

    status_code = 502
    code = "ai_provider_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
        details: Any = None,
    ) -> None:
        super().__init__(message, code=code or "ai_provider_error", details=details)
        self.retryable = retryable


class AIResponseInvalidError(AIProviderError):
    def __init__(self, message: str = "AI response did not match the expected schema.") -> None:
        super().__init__(message, code="ai_response_invalid")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, details=exc.details, request_id=_request_id(request)),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else DEFAULT_MESSAGES.get(
        exc.status_code, "Request failed."
    )
    code = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        429: "rate_limited",
    }.get(exc.status_code, "http_error")
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, request_id=_request_id(request)),
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", []) if part != "body"]
        details.append(
            {
                "field": ".".join(loc) or "body",
                "message": err.get("msg", "Invalid value."),
                "type": err.get("type", "value_error"),
            }
        )
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed.",
            details=details,
            request_id=_request_id(request),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak stack traces or secrets to the client.
    return JSONResponse(
        status_code=500,
        content=error_body(
            "internal_error",
            DEFAULT_MESSAGES[500],
            request_id=_request_id(request),
        ),
    )
