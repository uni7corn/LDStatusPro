"""Pydantic schemas for the Tickets domain."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TicketCreateRequest(BaseModel):
    type_name: str
    title: str
    content: str


class TicketReplyRequest(BaseModel):
    content: str


class TicketTypeUpdate(BaseModel):
    types: list[dict]
