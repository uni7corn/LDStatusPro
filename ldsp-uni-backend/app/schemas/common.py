"""Shared schemas for pagination and common response structures."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=200)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
