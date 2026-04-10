"""Pydantic schemas for the Products domain."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ProductCreateRequest(BaseModel):
    """Request for creating/submitting a product."""

    name: str
    description: str = ""
    category_id: int = 0
    price: float = 0.0
    contact_method: str = ""
    product_type: str = "normal"  # normal, cdk
    images: list[str] = []
    tags: list[str] = []


class ProductUpdateRequest(BaseModel):
    """Request for updating a product."""

    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    price: float | None = None
    contact_method: str | None = None
    images: list[str] | None = None
    tags: list[str] | None = None
