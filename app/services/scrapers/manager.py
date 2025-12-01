"""Scraper manager for coordinating multiple scrapers."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Type, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import ScrapingSource, ScrapingRun, OperationType
from app.services.scrapers.base import BaseScraper, ScraperResult
from app.services.deduplication.service import DeduplicationService
from app.services.property_service import PropertyService

logger = logging.getLogger(__name__)


class ScraperManager:
    """
    Manager for coordinating multiple property scrapers.

    Handles:
    - Scraper registration and discovery
    - Coordinated scraping across multiple sources
    - Deduplication integration
    - Run tracking and statistics
    """

    def __init__(self, db: AsyncSession):
        """Initialize scraper manager."""
        self.db = db
        self._scrapers: Dict[str, Type[BaseScraper]] = {}
        self._dedup_service = DeduplicationService(db)
        self._property_service = PropertyService(db)

    def register_scraper(self, scraper_class: Type[BaseScraper]):
        """Register a scraper class."""
        self._scrapers[scraper_class.name] = scraper_class
        logger.info(f"Registered scraper: {scraper_class.name}")

    def get_scraper(self, name: str) -> Optional[Type[BaseScraper]]:
        """Get a registered scraper by name."""
        return self._scrapers.get(name)

    def list_scrapers(self) -> List[str]:
        """List all registered scraper names."""
        return list(self._scrapers.keys())

    async def run_scraper(
        self,
        source: ScrapingSource,
        operation_type: OperationType,
        city: str,
        max_properties: Optional[int] = None,
        **filters,
    ) -> ScrapingRun:
        """
        Run a scraper for a specific source.

        Args:
            source: Scraping source configuration
            operation_type: Sale or rent
            city: City to search
            max_properties: Maximum properties to scrape
            **filters: Additional search filters

        Returns:
            ScrapingRun with statistics
        """
        scraper_class = self._scrapers.get(source.scraper_class)
        if not scraper_class:
            raise ValueError(f"Unknown scraper: {source.scraper_class}")

        # Create scraping run record
        run = ScrapingRun(
            source_id=source.id,
            started_at=datetime.utcnow(),
            status="running",
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        errors = []
        try:
            async with scraper_class(source.config) as scraper:
                async for result in scraper.scrape_listings(
                    operation_type=operation_type,
                    city=city,
                    max_properties=max_properties,
                    **filters,
                ):
                    run.properties_found += 1

                    try:
                        # Check for duplicates
                        is_duplicate, duplicate_id = await self._dedup_service.check_duplicate(
                            result
                        )

                        if is_duplicate:
                            run.properties_duplicates += 1
                            logger.debug(f"Duplicate found: {result.source_url}")
                            continue

                        # Check if property already exists by URL
                        existing = await self._property_service.get_by_url(result.source_url)

                        if existing:
                            # Update existing property
                            await self._property_service.update_from_scraper(
                                existing.id, result
                            )
                            run.properties_updated += 1
                        else:
                            # Create new property
                            await self._property_service.create_from_scraper(
                                result, source.id
                            )
                            run.properties_new += 1

                    except Exception as e:
                        logger.error(f"Error processing {result.source_url}: {e}")
                        errors.append({
                            "url": result.source_url,
                            "error": str(e),
                        })

            run.status = "completed"

        except Exception as e:
            logger.error(f"Scraper run failed: {e}")
            run.status = "failed"
            errors.append({"error": str(e)})

        finally:
            run.finished_at = datetime.utcnow()
            run.errors = errors
            await self.db.commit()
            await self.db.refresh(run)

        return run

    async def run_all_scrapers(
        self,
        operation_type: OperationType,
        city: str,
        max_properties_per_source: Optional[int] = None,
        **filters,
    ) -> List[ScrapingRun]:
        """
        Run all active scrapers concurrently.

        Args:
            operation_type: Sale or rent
            city: City to search
            max_properties_per_source: Max properties per scraper
            **filters: Additional filters

        Returns:
            List of ScrapingRun records
        """
        from sqlalchemy import select

        # Get all active sources
        result = await self.db.execute(
            select(ScrapingSource).where(ScrapingSource.is_active == True)
        )
        sources = result.scalars().all()

        # Run scrapers concurrently
        tasks = [
            self.run_scraper(
                source=source,
                operation_type=operation_type,
                city=city,
                max_properties=max_properties_per_source,
                **filters,
            )
            for source in sources
            if source.scraper_class in self._scrapers
        ]

        runs = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        return [r for r in runs if isinstance(r, ScrapingRun)]
