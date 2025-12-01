"""Scraping management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.property import ScrapingSource, ScrapingRun, OperationType

router = APIRouter()


class ScrapingRunResponse(BaseModel):
    """Schema for scraping run response."""

    id: int
    source_id: int
    started_at: str
    finished_at: Optional[str]
    status: str
    properties_found: int
    properties_new: int
    properties_updated: int
    properties_duplicates: int
    errors: List[dict]

    class Config:
        from_attributes = True


class StartScrapingRequest(BaseModel):
    """Schema for starting a scraping job."""

    source_id: int
    operation_type: OperationType
    city: str
    max_properties: Optional[int] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    bedrooms_min: Optional[int] = None


@router.get("/runs", response_model=List[ScrapingRunResponse])
async def list_scraping_runs(
    source_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List scraping runs."""
    query = select(ScrapingRun).order_by(ScrapingRun.started_at.desc()).limit(limit)

    if source_id:
        query = query.where(ScrapingRun.source_id == source_id)

    if status:
        query = query.where(ScrapingRun.status == status)

    result = await db.execute(query)
    runs = result.scalars().all()

    return runs


@router.get("/runs/{run_id}", response_model=ScrapingRunResponse)
async def get_scraping_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a scraping run by ID."""
    result = await db.execute(
        select(ScrapingRun).where(ScrapingRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Scraping run not found")

    return run


@router.post("/start", response_model=ScrapingRunResponse, status_code=202)
async def start_scraping(
    request: StartScrapingRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a scraping job.

    The scraping job runs in the background. Use the returned run ID
    to track progress.
    """
    # Get source
    result = await db.execute(
        select(ScrapingSource).where(ScrapingSource.id == request.source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if not source.is_active:
        raise HTTPException(status_code=400, detail="Source is not active")

    # Create run record
    run = ScrapingRun(
        source_id=source.id,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Add background task
    # Note: In production, you would use a proper task queue like Celery
    background_tasks.add_task(
        run_scraper_task,
        run_id=run.id,
        source_id=source.id,
        operation_type=request.operation_type,
        city=request.city,
        max_properties=request.max_properties,
        price_min=request.price_min,
        price_max=request.price_max,
        bedrooms_min=request.bedrooms_min,
    )

    return run


async def run_scraper_task(
    run_id: int,
    source_id: int,
    operation_type: OperationType,
    city: str,
    max_properties: Optional[int] = None,
    **filters,
):
    """
    Background task for running a scraper.

    Note: In production, this should be a Celery task or similar
    to handle proper process isolation and retries.
    """
    from app.db.session import AsyncSessionLocal
    from app.services.scrapers.manager import ScraperManager

    async with AsyncSessionLocal() as db:
        # Get source and run
        result = await db.execute(
            select(ScrapingSource).where(ScrapingSource.id == source_id)
        )
        source = result.scalar_one_or_none()

        result = await db.execute(
            select(ScrapingRun).where(ScrapingRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not source or not run:
            return

        # Initialize scraper manager
        manager = ScraperManager(db)

        # Register available scrapers
        from app.services.scrapers.example_scraper import ExampleScraper
        manager.register_scraper(ExampleScraper)

        try:
            # Run scraper
            await manager.run_scraper(
                source=source,
                operation_type=operation_type,
                city=city,
                max_properties=max_properties,
                **{k: v for k, v in filters.items() if v is not None},
            )
        except Exception as e:
            run.status = "failed"
            run.errors = [{"error": str(e)}]
            await db.commit()
