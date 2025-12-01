"""
Scraper for Inmuebles24 (Mexico) - Real Estate Portal.

Extracts property listings from specific neighborhoods (colonias) in CDMX.
Uses httpx + BeautifulSoup with Playwright fallback for JavaScript-rendered content.
"""

import asyncio
import json
import logging
import re
from decimal import Decimal
from typing import Optional, Dict, Any, List, AsyncIterator
from urllib.parse import urljoin, quote

from bs4 import BeautifulSoup
import httpx

from app.models.property import PropertyType, OperationType
from app.services.scrapers.base import BaseScraper, ScraperResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PlaywrightFetcher:
    """Fallback fetcher using Playwright for JavaScript-rendered pages."""

    def __init__(self):
        self._browser = None
        self._playwright = None

    async def setup(self):
        """Initialize Playwright browser."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            logger.info("Playwright browser initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Playwright: {e}")
            self._browser = None

    async def teardown(self):
        """Clean up Playwright resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch(self, url: str, wait_selector: str = None) -> Optional[str]:
        """Fetch page content using Playwright."""
        if not self._browser:
            return None

        page = None
        try:
            page = await self._browser.new_page()

            # Set realistic viewport and user agent
            await page.set_viewport_size({"width": 1920, "height": 1080})

            # Navigate to page
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for specific selector if provided
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass

            # Small delay for dynamic content
            await asyncio.sleep(2)

            content = await page.content()
            return content

        except Exception as e:
            logger.error(f"Playwright fetch failed for {url}: {e}")
            return None

        finally:
            if page:
                await page.close()


class Inmuebles24Scraper(BaseScraper):
    """
    Scraper for Inmuebles24 Mexico.

    Supports searching properties in specific colonias (neighborhoods) of CDMX.
    Handles both static HTML and JavaScript-rendered content.
    """

    name = "inmuebles24"
    base_url = "https://www.inmuebles24.com"

    # Mapping of common property types from Inmuebles24
    PROPERTY_TYPE_MAP = {
        "departamento": PropertyType.APARTMENT,
        "departamentos": PropertyType.APARTMENT,
        "casa": PropertyType.HOUSE,
        "casas": PropertyType.HOUSE,
        "terreno": PropertyType.LAND,
        "terrenos": PropertyType.LAND,
        "oficina": PropertyType.OFFICE,
        "oficinas": PropertyType.OFFICE,
        "local": PropertyType.COMMERCIAL,
        "locales": PropertyType.COMMERCIAL,
        "bodega": PropertyType.WAREHOUSE,
        "bodegas": PropertyType.WAREHOUSE,
        "penthouse": PropertyType.PENTHOUSE,
        "loft": PropertyType.LOFT,
    }

    # CDMX Colonias slug mapping (common neighborhoods)
    CDMX_COLONIAS = {
        "polanco": "polanco",
        "condesa": "condesa",
        "roma norte": "roma-norte",
        "roma sur": "roma-sur",
        "del valle": "del-valle",
        "narvarte": "narvarte",
        "napoles": "napoles",
        "san angel": "san-angel",
        "coyoacan": "coyoacan",
        "santa fe": "santa-fe",
        "interlomas": "interlomas",
        "pedregal": "pedregal",
        "lomas de chapultepec": "lomas-de-chapultepec",
        "anzures": "anzures",
        "escandon": "escandon",
        "juarez": "juarez",
        "cuauhtemoc": "cuauhtemoc",
        "hipodromo": "hipodromo",
        "hipodromo condesa": "hipodromo-condesa",
        "san miguel chapultepec": "san-miguel-chapultepec",
        "mixcoac": "mixcoac",
        "tlalpan": "tlalpan",
        "xochimilco": "xochimilco",
        "benito juarez": "benito-juarez",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Inmuebles24 scraper."""
        super().__init__(config)
        self._playwright_fetcher: Optional[PlaywrightFetcher] = None
        self._use_playwright_fallback = config.get("use_playwright", True) if config else True
        self._failed_urls: set = set()

    async def setup(self):
        """Set up scraper with enhanced headers for Inmuebles24."""
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=30.0,
            follow_redirects=True,
        )

        # Initialize Playwright fallback if enabled
        if self._use_playwright_fallback:
            self._playwright_fetcher = PlaywrightFetcher()
            await self._playwright_fetcher.setup()

    async def teardown(self):
        """Clean up all resources."""
        await super().teardown()
        if self._playwright_fetcher:
            await self._playwright_fetcher.teardown()

    def _normalize_colonia(self, colonia: str) -> str:
        """Normalize colonia name to URL slug."""
        colonia_lower = colonia.lower().strip()

        # Check if we have a direct mapping
        if colonia_lower in self.CDMX_COLONIAS:
            return self.CDMX_COLONIAS[colonia_lower]

        # Generate slug from name
        slug = colonia_lower.replace(" ", "-")
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        return slug

    def _build_search_url(
        self,
        operation_type: OperationType,
        colonia: str,
        page: int = 1,
        **filters,
    ) -> str:
        """Build search URL for Inmuebles24."""
        # Operation type path
        if operation_type == OperationType.SALE:
            operation_path = "venta"
        elif operation_type == OperationType.RENT:
            operation_path = "renta"
        else:
            operation_path = "venta"

        # Property type (default to all residential)
        property_type = filters.get("property_type", "inmuebles")

        # Normalize colonia to slug
        colonia_slug = self._normalize_colonia(colonia)

        # Build base URL
        # Format: /departamentos-o-casas-en-venta-en-condesa.html
        url = f"{self.base_url}/{property_type}-en-{operation_path}-en-{colonia_slug}.html"

        # Add filters as query parameters
        params = []

        if filters.get("price_min"):
            params.append(f"precio-desde-{filters['price_min']}")

        if filters.get("price_max"):
            params.append(f"precio-hasta-{filters['price_max']}")

        if filters.get("bedrooms_min"):
            params.append(f"con-{filters['bedrooms_min']}-recamaras")

        if filters.get("area_min"):
            params.append(f"desde-{filters['area_min']}-m2")

        # Pagination
        if page > 1:
            params.append(f"pagina-{page}")

        if params:
            url = url.replace(".html", f"-{'-'.join(params)}.html")

        return url

    async def _fetch_with_fallback(
        self,
        url: str,
        wait_selector: str = None,
    ) -> Optional[str]:
        """Fetch URL with httpx, fallback to Playwright if needed."""
        # Try httpx first
        try:
            await self._rate_limit()
            response = await self._client.get(url)
            response.raise_for_status()
            self._request_count += 1

            content = response.text

            # Check if we got a valid response (not a captcha or block page)
            if self._is_valid_response(content):
                return content

            logger.warning(f"Invalid response from httpx for {url}, trying Playwright")

        except httpx.HTTPError as e:
            logger.warning(f"httpx request failed for {url}: {e}")

        # Fallback to Playwright
        if self._playwright_fetcher and self._use_playwright_fallback:
            logger.info(f"Using Playwright fallback for {url}")
            content = await self._playwright_fetcher.fetch(url, wait_selector)
            if content and self._is_valid_response(content):
                return content

        self._failed_urls.add(url)
        return None

    def _is_valid_response(self, content: str) -> bool:
        """Check if the response contains valid property data."""
        if not content:
            return False

        # Check for common block/captcha indicators
        block_indicators = [
            "captcha",
            "robot",
            "blocked",
            "access denied",
            "rate limit",
        ]

        content_lower = content.lower()
        for indicator in block_indicators:
            if indicator in content_lower and "recaptcha" not in content_lower:
                return False

        # Check for property listing indicators
        valid_indicators = [
            "postingcard",
            "listing",
            "property",
            "inmueble",
            "precio",
        ]

        for indicator in valid_indicators:
            if indicator in content_lower:
                return True

        return len(content) > 5000  # Assume valid if reasonably sized

    async def get_listing_urls(
        self,
        operation_type: OperationType,
        city: str,
        **filters,
    ) -> AsyncIterator[str]:
        """
        Get property URLs from Inmuebles24 listing pages.

        Args:
            operation_type: Sale or rent
            city: City/colonia to search (e.g., "condesa", "polanco")
            **filters: Additional filters
                - colonias: List of colonias to search
                - price_min: Minimum price
                - price_max: Maximum price
                - bedrooms_min: Minimum bedrooms
                - max_pages: Maximum pages to scrape (default 10)

        Yields:
            Property detail page URLs
        """
        colonias = filters.pop("colonias", [city])
        if isinstance(colonias, str):
            colonias = [colonias]

        max_pages = filters.pop("max_pages", 10)
        seen_urls = set()

        for colonia in colonias:
            logger.info(f"Scraping listings for colonia: {colonia}")
            page = 1

            while page <= max_pages:
                url = self._build_search_url(
                    operation_type=operation_type,
                    colonia=colonia,
                    page=page,
                    **filters,
                )

                logger.debug(f"Fetching listing page: {url}")

                content = await self._fetch_with_fallback(
                    url,
                    wait_selector="[data-qa='posting']"
                )

                if not content:
                    logger.warning(f"Failed to fetch listing page: {url}")
                    break

                soup = BeautifulSoup(content, "lxml")

                # Find property cards
                property_urls = self._extract_listing_urls(soup)

                if not property_urls:
                    logger.info(f"No more properties found on page {page} for {colonia}")
                    break

                new_urls_count = 0
                for prop_url in property_urls:
                    if prop_url not in seen_urls:
                        seen_urls.add(prop_url)
                        new_urls_count += 1
                        yield prop_url

                logger.info(
                    f"Found {new_urls_count} new properties on page {page} for {colonia}"
                )

                # Check if there's a next page
                if not self._has_next_page(soup):
                    break

                page += 1
                await asyncio.sleep(1)  # Extra delay between pages

    def _extract_listing_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract property URLs from listing page."""
        urls = []

        # Try multiple selectors for property cards
        selectors = [
            "[data-qa='posting'] a[data-qa='posting-title']",
            "div.postingCard a.go-to-posting",
            "div[data-posting-type] a[href*='/propiedades/']",
            "a[href*='/propiedades/'][class*='posting']",
            ".posting-card a[href*='/propiedades/']",
        ]

        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                for card in cards:
                    href = card.get("href")
                    if href:
                        if not href.startswith("http"):
                            href = urljoin(self.base_url, href)
                        if "/propiedades/" in href and href not in urls:
                            urls.append(href)
                break

        # Fallback: find all links to property pages
        if not urls:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                href = link["href"]
                if "/propiedades/" in href and "inmuebles24.com" in href:
                    if not href.startswith("http"):
                        href = urljoin(self.base_url, href)
                    if href not in urls:
                        urls.append(href)

        return urls

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """Check if there's a next page of results."""
        # Look for pagination
        next_selectors = [
            "a[data-qa='pagination-next']",
            "a.pagination-next",
            "li.pagination-next a",
            "a[rel='next']",
        ]

        for selector in next_selectors:
            next_btn = soup.select_one(selector)
            if next_btn and next_btn.get("href"):
                return True

        return False

    async def scrape_property(self, url: str) -> Optional[ScraperResult]:
        """
        Scrape a single property detail page from Inmuebles24.

        Args:
            url: Property detail page URL

        Returns:
            ScraperResult with property data, or None if scraping failed
        """
        logger.debug(f"Scraping property: {url}")

        content = await self._fetch_with_fallback(
            url,
            wait_selector="[data-qa='posting-price']"
        )

        if not content:
            logger.error(f"Failed to fetch property page: {url}")
            return None

        try:
            soup = BeautifulSoup(content, "lxml")
            return self._parse_property_page(soup, url)
        except Exception as e:
            logger.error(f"Error parsing property {url}: {e}")
            return None

    def _parse_property_page(
        self,
        soup: BeautifulSoup,
        url: str,
    ) -> Optional[ScraperResult]:
        """Parse property detail page and extract data."""
        # Extract external ID from URL
        external_id = self._extract_external_id(url)

        # Title
        title = self._extract_title(soup)
        if not title:
            logger.warning(f"No title found for {url}")
            return None

        # Price
        price = self._extract_price(soup)
        if not price:
            logger.warning(f"No price found for {url}")
            return None

        # Location info
        address, neighborhood, city = self._extract_location(soup)

        # Property characteristics
        area = self._extract_area(soup)
        bedrooms = self._extract_bedrooms(soup)
        bathrooms = self._extract_bathrooms(soup)

        # Property and operation type
        property_type = self._extract_property_type(soup, url)
        operation_type = self._extract_operation_type(url)

        # Description
        description = self._extract_description(soup)

        # Images
        images = self._extract_images(soup)

        # Additional features
        features = self._extract_features(soup)

        # Coordinates (if available in JSON-LD or data attributes)
        latitude, longitude = self._extract_coordinates(soup)

        # Additional details
        floor = self._extract_floor(soup)
        parking = self._extract_parking(soup)
        amenities = self._extract_amenities(soup)

        return ScraperResult(
            source_url=url,
            external_id=external_id,
            title=title,
            description=description,
            price=price,
            price_currency="MXN",
            city=city or "Ciudad de México",
            property_type=property_type,
            operation_type=operation_type,
            address=address,
            neighborhood=neighborhood,
            province="Ciudad de México",
            latitude=latitude,
            longitude=longitude,
            area_built=area,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            floor=floor,
            has_parking=parking.get("has_parking"),
            parking_spaces=parking.get("spaces"),
            has_elevator=amenities.get("elevator"),
            has_pool=amenities.get("pool"),
            has_gym=amenities.get("gym") if hasattr(ScraperResult, "has_gym") else None,
            has_terrace=amenities.get("terrace"),
            has_balcony=amenities.get("balcony"),
            has_garden=amenities.get("garden"),
            images=images,
            features=features,
            raw_data={
                "url": url,
                "external_id": external_id,
                "amenities": amenities,
            },
        )

    def _extract_external_id(self, url: str) -> Optional[str]:
        """Extract property ID from URL."""
        # URL format: /propiedades/departamento-en-venta-xxx-12345678.html
        match = re.search(r"-(\d+)\.html", url)
        if match:
            return match.group(1)

        # Alternative format
        match = re.search(r"/(\d+)$", url.rstrip("/"))
        return match.group(1) if match else None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property title."""
        selectors = [
            "h1[data-qa='posting-title']",
            "h1.posting-title",
            "h1.title-property",
            "h1",
        ]

        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                title = el.get_text(strip=True)
                if title and len(title) > 5:
                    return title

        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract property price."""
        selectors = [
            "[data-qa='posting-price']",
            ".posting-price",
            ".price-value",
            "span.price",
        ]

        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                price_text = el.get_text(strip=True)
                price = self._parse_price(price_text)
                if price:
                    return price

        # Try JSON-LD
        json_ld = self._extract_json_ld(soup)
        if json_ld and "offers" in json_ld:
            price = json_ld["offers"].get("price")
            if price:
                return Decimal(str(price))

        return None

    def _parse_price(self, price_text: str) -> Optional[Decimal]:
        """Parse price from text."""
        if not price_text:
            return None

        # Remove currency symbols and text
        price_clean = re.sub(r"[^\d.,]", "", price_text)

        # Handle Mexican number format (1,234,567.00 or 1.234.567,00)
        if "," in price_clean and "." in price_clean:
            # Determine format
            if price_clean.rfind(",") > price_clean.rfind("."):
                # European format: 1.234.567,00
                price_clean = price_clean.replace(".", "").replace(",", ".")
            else:
                # US format: 1,234,567.00
                price_clean = price_clean.replace(",", "")
        elif "," in price_clean:
            # Could be thousands separator or decimal
            if len(price_clean.split(",")[-1]) == 2:
                price_clean = price_clean.replace(",", ".")
            else:
                price_clean = price_clean.replace(",", "")

        try:
            return Decimal(price_clean)
        except Exception:
            return None

    def _extract_location(
        self,
        soup: BeautifulSoup,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract address, neighborhood, and city."""
        address = None
        neighborhood = None
        city = "Ciudad de México"

        # Try location element
        location_selectors = [
            "[data-qa='posting-location']",
            ".posting-location",
            ".location-text",
            "span.location",
        ]

        for selector in location_selectors:
            el = soup.select_one(selector)
            if el:
                location_text = el.get_text(strip=True)
                parts = [p.strip() for p in location_text.split(",")]

                if len(parts) >= 1:
                    neighborhood = parts[0]
                if len(parts) >= 2:
                    # Could be delegación or city
                    if "ciudad de méxico" in parts[-1].lower() or "cdmx" in parts[-1].lower():
                        city = "Ciudad de México"
                    else:
                        city = parts[-1]
                if len(parts) >= 3:
                    address = ", ".join(parts[:-2])
                break

        # Try address element specifically
        addr_el = soup.select_one("[data-qa='posting-address'], .posting-address")
        if addr_el:
            address = addr_el.get_text(strip=True)

        return address, neighborhood, city

    def _extract_area(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract built area in square meters."""
        selectors = [
            "[data-qa='posting-area']",
            ".posting-area",
            "span[title*='m²']",
            "span[title*='superficie']",
        ]

        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                area_text = el.get_text(strip=True)
                match = re.search(r"(\d+(?:[.,]\d+)?)", area_text)
                if match:
                    return Decimal(match.group(1).replace(",", "."))

        # Look in features list
        features_text = soup.get_text()
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", features_text)
        if match:
            return Decimal(match.group(1).replace(",", "."))

        return None

    def _extract_bedrooms(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract number of bedrooms."""
        selectors = [
            "[data-qa='posting-bedrooms']",
            ".posting-bedrooms",
            "span[title*='recámara']",
            "span[title*='habitacion']",
        ]

        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                match = re.search(r"(\d+)", text)
                if match:
                    return int(match.group(1))

        # Look in features
        text = soup.get_text().lower()
        match = re.search(r"(\d+)\s*(?:recámara|habitacion|dormitorio)", text)
        if match:
            return int(match.group(1))

        return None

    def _extract_bathrooms(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract number of bathrooms."""
        selectors = [
            "[data-qa='posting-bathrooms']",
            ".posting-bathrooms",
            "span[title*='baño']",
        ]

        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                match = re.search(r"(\d+)", text)
                if match:
                    return int(match.group(1))

        # Look in features
        text = soup.get_text().lower()
        match = re.search(r"(\d+)\s*baño", text)
        if match:
            return int(match.group(1))

        return None

    def _extract_property_type(
        self,
        soup: BeautifulSoup,
        url: str,
    ) -> PropertyType:
        """Determine property type from page content or URL."""
        # Check URL
        url_lower = url.lower()
        for key, prop_type in self.PROPERTY_TYPE_MAP.items():
            if key in url_lower:
                return prop_type

        # Check title and content
        title = self._extract_title(soup) or ""
        title_lower = title.lower()

        for key, prop_type in self.PROPERTY_TYPE_MAP.items():
            if key in title_lower:
                return prop_type

        return PropertyType.APARTMENT  # Default for CDMX

    def _extract_operation_type(self, url: str) -> OperationType:
        """Determine operation type from URL."""
        url_lower = url.lower()
        if "renta" in url_lower or "alquiler" in url_lower:
            return OperationType.RENT
        return OperationType.SALE

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property description."""
        selectors = [
            "[data-qa='posting-description']",
            ".posting-description",
            ".description-content",
            "#description",
        ]

        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                # Get text and clean up
                description = el.get_text(separator=" ", strip=True)
                # Remove excessive whitespace
                description = re.sub(r"\s+", " ", description)
                if len(description) > 20:
                    return description

        return None

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract image URLs."""
        images = []

        # Try gallery images
        img_selectors = [
            "[data-qa='gallery-img'] img",
            ".gallery-image img",
            ".posting-gallery img",
            "img[data-flickity-lazyload]",
            ".carousel img",
        ]

        for selector in img_selectors:
            imgs = soup.select(selector)
            for img in imgs:
                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-flickity-lazyload")
                    or img.get("data-lazy")
                )
                if src and src not in images:
                    if not src.startswith("http"):
                        src = urljoin(self.base_url, src)
                    # Skip placeholder images
                    if "placeholder" not in src.lower() and "blank" not in src.lower():
                        images.append(src)

        # Try JSON-LD
        json_ld = self._extract_json_ld(soup)
        if json_ld and "image" in json_ld:
            img_data = json_ld["image"]
            if isinstance(img_data, list):
                images.extend([i for i in img_data if i not in images])
            elif isinstance(img_data, str) and img_data not in images:
                images.append(img_data)

        return images[:20]  # Limit to 20 images

    def _extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract list of property features/amenities."""
        features = []

        feature_selectors = [
            "[data-qa='posting-feature']",
            ".posting-feature",
            ".feature-item",
            ".amenity-item",
            "li.feature",
        ]

        for selector in feature_selectors:
            items = soup.select(selector)
            for item in items:
                text = item.get_text(strip=True)
                if text and text not in features:
                    features.append(text)

        return features

    def _extract_coordinates(
        self,
        soup: BeautifulSoup,
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Extract latitude and longitude from page."""
        # Try JSON-LD
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            geo = json_ld.get("geo", {})
            lat = geo.get("latitude")
            lng = geo.get("longitude")
            if lat and lng:
                return Decimal(str(lat)), Decimal(str(lng))

        # Try data attributes
        map_el = soup.select_one("[data-lat][data-lng], [data-latitude][data-longitude]")
        if map_el:
            lat = map_el.get("data-lat") or map_el.get("data-latitude")
            lng = map_el.get("data-lng") or map_el.get("data-longitude")
            if lat and lng:
                try:
                    return Decimal(lat), Decimal(lng)
                except Exception:
                    pass

        # Try to find in script tags
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    lat = data.get("latitude") or data.get("lat")
                    lng = data.get("longitude") or data.get("lng")
                    if lat and lng:
                        return Decimal(str(lat)), Decimal(str(lng))
            except Exception:
                pass

        return None, None

    def _extract_floor(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract floor number."""
        text = soup.get_text().lower()
        match = re.search(r"piso\s*(\d+)|(\d+)\s*(?:er|do|to|vo|no)?\s*piso", text)
        if match:
            return int(match.group(1) or match.group(2))

        # Look for "planta baja" = ground floor
        if "planta baja" in text:
            return 0

        return None

    def _extract_parking(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract parking information."""
        result = {"has_parking": None, "spaces": None}

        text = soup.get_text().lower()

        # Look for parking spaces
        match = re.search(r"(\d+)\s*(?:lugar|espacio|cajón)(?:es)?\s*(?:de\s*)?estacionamiento", text)
        if match:
            result["has_parking"] = True
            result["spaces"] = int(match.group(1))
            return result

        # General parking mention
        if any(word in text for word in ["estacionamiento", "garage", "cochera", "parking"]):
            result["has_parking"] = True
            result["spaces"] = 1

        return result

    def _extract_amenities(self, soup: BeautifulSoup) -> Dict[str, bool]:
        """Extract amenities as boolean flags."""
        text = soup.get_text().lower()
        features = " ".join(self._extract_features(soup)).lower()
        combined = text + " " + features

        return {
            "elevator": any(w in combined for w in ["elevador", "ascensor"]),
            "pool": any(w in combined for w in ["alberca", "piscina"]),
            "gym": any(w in combined for w in ["gimnasio", "gym"]),
            "terrace": any(w in combined for w in ["terraza", "roof"]),
            "balcony": "balcón" in combined or "balcon" in combined,
            "garden": any(w in combined for w in ["jardín", "jardin", "áreas verdes"]),
            "security": any(w in combined for w in ["vigilancia", "seguridad", "cctv"]),
            "air_conditioning": any(w in combined for w in ["aire acondicionado", "clima", "a/c"]),
        }

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract JSON-LD structured data from page."""
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") in ["RealEstateListing", "Product", "Residence"]:
                        return data
                elif isinstance(data, list):
                    for item in data:
                        if item.get("@type") in ["RealEstateListing", "Product", "Residence"]:
                            return item
            except Exception:
                continue

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get scraper statistics including failed URLs."""
        stats = super().get_stats()
        stats["failed_urls"] = len(self._failed_urls)
        return stats
