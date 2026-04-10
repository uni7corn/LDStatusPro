"""SQLAlchemy models for the Users domain."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    site: Mapped[str] = mapped_column(sa.String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(50), primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(100))
    name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    trust_level: Mapped[int] = mapped_column(sa.Integer, default=0)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    cloud_sync_only: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    joined_at: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    last_sync: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    created_at: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    updated_at: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    quit_at: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
