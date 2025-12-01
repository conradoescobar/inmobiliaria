"""Main API router."""

from fastapi import APIRouter

from app.api.endpoints import properties, sources, scraping, health

api_router = APIRouter()

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"],
)

api_router.include_router(
    properties.router,
    prefix="/properties",
    tags=["properties"],
)

api_router.include_router(
    sources.router,
    prefix="/sources",
    tags=["sources"],
)

api_router.include_router(
    scraping.router,
    prefix="/scraping",
    tags=["scraping"],
)
