"""CORS middleware configuration."""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from starlette.applications import Starlette


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8790",
]


def setup_cors(app: Starlette) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
