"""Scraping management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
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


class Inmuebles24ScrapingRequest(BaseModel):
    """Schema for starting an Inmuebles24 scraping job for CDMX colonias."""

    colonias: List[str] = Field(
        ...,
        description="List of CDMX colonias (neighborhoods) to search",
        examples=[["condesa", "roma norte", "polanco"]],
    )
    operation_type: OperationType = Field(
        default=OperationType.SALE,
        description="Operation type: sale or rent",
    )
    max_properties: Optional[int] = Field(
        default=None,
        description="Maximum number of properties to scrape (None for unlimited)",
    )
    max_pages: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum pages to scrape per colonia",
    )
    price_min: Optional[int] = Field(
        default=None,
        ge=0,
        description="Minimum price in MXN",
    )
    price_max: Optional[int] = Field(
        default=None,
        ge=0,
        description="Maximum price in MXN",
    )
    bedrooms_min: Optional[int] = Field(
        default=None,
        ge=0,
        description="Minimum number of bedrooms",
    )
    property_type: str = Field(
        default="departamentos-o-casas",
        description="Property type slug (departamentos, casas, departamentos-o-casas)",
    )
    use_playwright: bool = Field(
        default=True,
        description="Use Playwright as fallback for JavaScript-rendered content",
    )


class ScraperStatsResponse(BaseModel):
    """Schema for scraper statistics."""

    name: str
    request_count: int
    failed_urls: int
    status: str


# Available CDMX colonias for reference
CDMX_COLONIAS_LIST = [
    "polanco",
    "condesa",
    "roma norte",
    "roma sur",
    "del valle",
    "narvarte",
    "napoles",
    "san angel",
    "coyoacan",
    "santa fe",
    "interlomas",
    "pedregal",
    "lomas de chapultepec",
    "anzures",
    "escandon",
    "juarez",
    "cuauhtemoc",
    "hipodromo",
    "hipodromo condesa",
    "san miguel chapultepec",
    "mixcoac",
    "tlalpan",
    "xochimilco",
    "benito juarez",
]


@router.get("/colonias", response_model=List[str])
async def list_cdmx_colonias():
    """List available CDMX colonias for Inmuebles24 scraping."""
    return sorted(CDMX_COLONIAS_LIST)


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
    Start a scraping job for a configured source.

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


@router.post("/inmuebles24/start", response_model=ScrapingRunResponse, status_code=202)
async def start_inmuebles24_scraping(
    request: Inmuebles24ScrapingRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Start an Inmuebles24 scraping job for CDMX colonias.

    This endpoint specifically targets Inmuebles24 Mexico and allows
    searching in multiple colonias (neighborhoods) of Ciudad de México.

    Example colonias: condesa, roma norte, polanco, del valle, etc.
    """
    # Get or create Inmuebles24 source
    result = await db.execute(
        select(ScrapingSource).where(ScrapingSource.name == "inmuebles24")
    )
    source = result.scalar_one_or_none()

    if not source:
        # Auto-create source if it doesn't exist
        source = ScrapingSource(
            name="inmuebles24",
            base_url="https://www.inmuebles24.com",
            scraper_class="inmuebles24",
            is_active=True,
            config={
                "use_playwright": request.use_playwright,
            },
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)

    # Create run record
    run = ScrapingRun(
        source_id=source.id,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Add background task
    background_tasks.add_task(
        run_inmuebles24_task,
        run_id=run.id,
        source_id=source.id,
        colonias=request.colonias,
        operation_type=request.operation_type,
        max_properties=request.max_properties,
        max_pages=request.max_pages,
        price_min=request.price_min,
        price_max=request.price_max,
        bedrooms_min=request.bedrooms_min,
        property_type=request.property_type,
        use_playwright=request.use_playwright,
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
        from app.services.scrapers.inmuebles24 import Inmuebles24Scraper

        manager.register_scraper(ExampleScraper)
        manager.register_scraper(Inmuebles24Scraper)

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


async def run_inmuebles24_task(
    run_id: int,
    source_id: int,
    colonias: List[str],
    operation_type: OperationType,
    max_properties: Optional[int] = None,
    max_pages: int = 10,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    bedrooms_min: Optional[int] = None,
    property_type: str = "departamentos-o-casas",
    use_playwright: bool = True,
):
    """
    Background task for running Inmuebles24 scraper with CDMX colonias.
    """
    import logging
    from datetime import datetime

    from app.db.session import AsyncSessionLocal
    from app.services.scrapers.inmuebles24 import Inmuebles24Scraper
    from app.services.deduplication.service import DeduplicationService
    from app.services.property_service import PropertyService

    logger = logging.getLogger(__name__)

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

        # Update run status
        run.status = "running"
        run.started_at = datetime.utcnow()
        await db.commit()

        # Initialize services
        dedup_service = DeduplicationService(db)
        property_service = PropertyService(db)

        errors = []
        scraper_config = {
            "use_playwright": use_playwright,
        }

        try:
            async with Inmuebles24Scraper(scraper_config) as scraper:
                # Build filters
                filters = {
                    "colonias": colonias,
                    "max_pages": max_pages,
                    "property_type": property_type,
                }

                if price_min:
                    filters["price_min"] = price_min
                if price_max:
                    filters["price_max"] = price_max
                if bedrooms_min:
                    filters["bedrooms_min"] = bedrooms_min

                logger.info(
                    f"Starting Inmuebles24 scrape for colonias: {colonias}"
                )

                property_count = 0
                async for prop_result in scraper.scrape_listings(
                    operation_type=operation_type,
                    city="ciudad-de-mexico",  # Base city
                    max_properties=max_properties,
                    **filters,
                ):
                    run.properties_found += 1
                    property_count += 1

                    try:
                        # Check for duplicates
                        is_duplicate, duplicate_id = await dedup_service.check_duplicate(
                            prop_result
                        )

                        if is_duplicate:
                            run.properties_duplicates += 1
                            logger.debug(
                                f"Duplicate found: {prop_result.source_url}"
                            )
                            continue

                        # Check if property already exists by URL
                        existing = await property_service.get_by_url(
                            prop_result.source_url
                        )

                        if existing:
                            # Update existing property
                            await property_service.update_from_scraper(
                                existing.id, prop_result
                            )
                            run.properties_updated += 1
                            logger.debug(f"Updated: {prop_result.source_url}")
                        else:
                            # Create new property
                            await property_service.create_from_scraper(
                                prop_result, source.id
                            )
                            run.properties_new += 1
                            logger.info(
                                f"New property: {prop_result.title[:50]}... "
                                f"({prop_result.neighborhood})"
                            )

                        # Commit periodically
                        if property_count % 10 == 0:
                            await db.commit()

                    except Exception as e:
                        logger.error(
                            f"Error processing {prop_result.source_url}: {e}"
                        )
                        errors.append({
                            "url": prop_result.source_url,
                            "error": str(e),
                        })

                # Get final scraper stats
                stats = scraper.get_stats()
                logger.info(
                    f"Scraper stats: {stats['request_count']} requests, "
                    f"{stats.get('failed_urls', 0)} failed URLs"
                )

            run.status = "completed"
            logger.info(
                f"Scraping completed: {run.properties_found} found, "
                f"{run.properties_new} new, {run.properties_updated} updated, "
                f"{run.properties_duplicates} duplicates"
            )

        except Exception as e:
            logger.error(f"Inmuebles24 scraper failed: {e}", exc_info=True)
            run.status = "failed"
            errors.append({"error": str(e)})

        finally:
            run.finished_at = datetime.utcnow()
            run.errors = errors
            await db.commit()
