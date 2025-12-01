"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter()


@router.get("")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/db")
async def database_health(db: AsyncSession = Depends(get_db)):
    """Check database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@router.get("/postgis")
async def postgis_health(db: AsyncSession = Depends(get_db)):
    """Check PostGIS extension."""
    try:
        result = await db.execute(text("SELECT PostGIS_Version()"))
        version = result.scalar()
        return {"status": "healthy", "postgis_version": version}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
