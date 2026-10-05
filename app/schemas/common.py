"""Shared response envelopes and pagination helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20
    pages: int = 0
    has_next: bool = False
    has_previous: bool = False


def paginate(items: list[T], total: int, page: int, page_size: int) -> Page[T]:
    pages = (total + page_size - 1) // page_size if page_size else 0
    return Page[T](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1,
    )


class OkResponse(BaseModel):
    ok: bool = True
    message: str | None = None


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    type: str | None = None


class ErrorEnvelope(BaseModel):
    code: str = Field(examples=["validation_error"])
    message: str
    details: list[ErrorDetail] | dict | list | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorEnvelope


class MessageResponse(BaseModel):
    message: str
