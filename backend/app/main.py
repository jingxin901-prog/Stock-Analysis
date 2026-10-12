"""FastAPI application entry point for QuantAI."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router

LOCAL_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
)


def allowed_origins() -> list[str]:
    """Return local origins plus exact public frontend origins from the environment."""

    configured = os.getenv("QUANTAI_CORS_ORIGINS", "")
    public_origins = [
        origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()
    ]
    return list(dict.fromkeys([*LOCAL_ORIGINS, *public_origins]))


def create_app() -> FastAPI:
    application = FastAPI(
        title="QuantAI Research API",
        description=(
            "Historical quantitative-finance research endpoints. Outputs are not investment advice."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(api_router, prefix="/api/v1")

    @application.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {
            "service": "QuantAI Research API",
            "documentation": "/docs",
            "disclaimer": "Research only; not investment advice.",
        }

    return application


app = create_app()
