"""Version-one API router."""

from fastapi import APIRouter

from app.api.v1.routes.dashboard import router as dashboard_router

api_router = APIRouter()
api_router.include_router(dashboard_router)
