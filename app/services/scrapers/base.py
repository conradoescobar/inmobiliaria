"""Base scraper class for real estate portals."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, AsyncIterator
import asyncio
import logging

import httpx

from app.core.config import get_settings
from app.models.property import PropertyType, OperationType

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class ScraperResult:
    """Result from scraping a single property."""

    # Required fields
    source_url: str
    title: str
    price: Decimal
    city: str
    property_type: PropertyType
    operation_type: OperationType

    # External identification
    external_id: Optional[str] = None

    # Description
    description: Optional[str] = None

    # Location
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None

    # Pricing
    price_currency: str = "EUR"
    community_fees: Optional[Decimal] = None

    # Characteristics
    area_built: Optional[Decimal] = None
    area_usable: Optional[Decimal] = None
    area_plot: Optional[Decimal] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    has_elevator: Optional[bool] = None
    has_parking: Optional[bool] = None
    parking_spaces: Optional[int] = None
    has_terrace: Optional[bool] = None
    has_balcony: Optional[bool] = None
    has_garden: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_storage: Optional[bool] = None
    has_air_conditioning: Optional[bool] = None
    has_heating: Optional[bool] = None
    heating_type: Optional[str] = None
    orientation: Optional[str] = None
    year_built: Optional[int] = None
    is_new_construction: bool = False
    needs_renovation: bool = False

    # Energy
    energy_rating: Optional[str] = None
    energy_consumption: Optional[Decimal] = None
    emissions_rating: Optional[str] = None

    # Images and features
    images: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)

    # Raw data for debugging
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)


class BaseScraper(ABC):
    """
    Abstract base class for real estate portal scrapers.

    Implement this class to create scrapers for specific portals.
    Each scraper should handle:
    - Listing page pagination
    - Property detail extraction
    - Rate limiting
    - Error handling
    """

    name: str = "base"
    base_url: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize scraper with optional configuration."""
        self.config = config or {}
        self._client: Optional[httpx.AsyncClient] = None
        self._request_count = 0
        self._last_request_time: Optional[datetime] = None

    async def __aenter__(self):
        """Enter async context."""
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        await self.teardown()

    async def setup(self):
        """Set up scraper resources."""
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.scraper_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    async def teardown(self):
        """Clean up scraper resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self):
        """Apply rate limiting between requests."""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            if elapsed < settings.scraper_delay_seconds:
                await asyncio.sleep(settings.scraper_delay_seconds - elapsed)
        self._last_request_time = datetime.utcnow()

    async def _fetch(self, url: str, **kwargs) -> httpx.Response:
        """Fetch URL with rate limiting and retry logic."""
        await self._rate_limit()

        for attempt in range(settings.scraper_max_retries):
            try:
                response = await self._client.get(url, **kwargs)
                response.raise_for_status()
                self._request_count += 1
                return response
            except httpx.HTTPError as e:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{settings.scraper_max_retries}): {e}"
                )
                if attempt < settings.scraper_max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

    @abstractmethod
    async def get_listing_urls(
        self,
        operation_type: OperationType,
        city: str,
        **filters,
    ) -> AsyncIterator[str]:
        """
        Get property URLs from listing pages.

        Args:
            operation_type: Sale or rent
            city: City to search in
            **filters: Additional filters (price range, bedrooms, etc.)

        Yields:
            Property detail page URLs
        """
        pass

    @abstractmethod
    async def scrape_property(self, url: str) -> Optional[ScraperResult]:
        """
        Scrape a single property detail page.

        Args:
            url: Property detail page URL

        Returns:
            ScraperResult with property data, or None if scraping failed
        """
        pass

    async def scrape_listings(
        self,
        operation_type: OperationType,
        city: str,
        max_properties: Optional[int] = None,
        **filters,
    ) -> AsyncIterator[ScraperResult]:
        """
        Scrape all properties from listings.

        Args:
            operation_type: Sale or rent
            city: City to search in
            max_properties: Maximum number of properties to scrape
            **filters: Additional filters

        Yields:
            ScraperResult for each property
        """
        count = 0
        async for url in self.get_listing_urls(operation_type, city, **filters):
            if max_properties and count >= max_properties:
                break

            try:
                result = await self.scrape_property(url)
                if result:
                    count += 1
                    yield result
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")
                continue

    def get_stats(self) -> Dict[str, Any]:
        """Get scraper statistics."""
        return {
            "name": self.name,
            "request_count": self._request_count,
            "last_request_time": self._last_request_time,
        }
