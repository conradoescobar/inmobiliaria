"""
Inmobiliaria Aggregator - Main Application

A real estate property aggregation platform that collects listings
from multiple portals and provides a unified API for searching.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info(f"Starting {settings.app_name}")
    logger.info(f"Debug mode: {settings.debug}")

    yield

    # Shutdown
    logger.info("Shutting down application")


app = FastAPI(
    title=settings.app_name,
    description="""
    ## Inmobiliaria Aggregator API

    A real estate property aggregation platform that:

    - **Aggregates listings** from multiple real estate portals
    - **Deduplicates properties** using address and feature similarity
    - **Provides geospatial search** using PostGIS
    - **Tracks price changes** over time

    ### Key Features

    - Modular scraper architecture for adding new property portals
    - Intelligent deduplication based on address normalization and feature matching
    - Geographic search with radius filtering
    - Comprehensive property filtering (price, area, rooms, amenities)
    - Price history tracking

    ### API Sections

    - **Properties**: CRUD operations and search
    - **Sources**: Manage scraping source configurations
    - **Scraping**: Control and monitor scraping jobs
    - **Health**: System health checks
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
