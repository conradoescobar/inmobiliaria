"""
Example scraper implementation.

This is a template showing how to implement a scraper for a real estate portal.
Adapt this to the specific portal you want to scrape.
"""

from decimal import Decimal
from typing import Optional, AsyncIterator
import re

from bs4 import BeautifulSoup

from app.models.property import PropertyType, OperationType
from app.services.scrapers.base import BaseScraper, ScraperResult


class ExampleScraper(BaseScraper):
    """
    Example scraper for demonstration purposes.

    This scraper shows the structure you should follow when implementing
    scrapers for real estate portals like Idealista, Fotocasa, etc.
    """

    name = "example"
    base_url = "https://example-portal.com"

    # Mapping of portal property types to our enum
    PROPERTY_TYPE_MAP = {
        "piso": PropertyType.APARTMENT,
        "casa": PropertyType.HOUSE,
        "chalet": PropertyType.HOUSE,
        "estudio": PropertyType.STUDIO,
        "atico": PropertyType.PENTHOUSE,
        "duplex": PropertyType.DUPLEX,
        "loft": PropertyType.LOFT,
        "terreno": PropertyType.LAND,
        "local": PropertyType.COMMERCIAL,
        "oficina": PropertyType.OFFICE,
        "nave": PropertyType.WAREHOUSE,
        "garaje": PropertyType.PARKING,
    }

    def _build_search_url(
        self,
        operation_type: OperationType,
        city: str,
        page: int = 1,
        **filters,
    ) -> str:
        """Build search URL for the portal."""
        operation = "venta" if operation_type == OperationType.SALE else "alquiler"
        url = f"{self.base_url}/{operation}/{city.lower()}"

        params = []
        if filters.get("price_min"):
            params.append(f"precio-desde_{filters['price_min']}")
        if filters.get("price_max"):
            params.append(f"precio-hasta_{filters['price_max']}")
        if filters.get("bedrooms_min"):
            params.append(f"habitaciones_{filters['bedrooms_min']}")

        if params:
            url += "/" + ",".join(params)

        if page > 1:
            url += f"/pagina-{page}"

        return url

    async def get_listing_urls(
        self,
        operation_type: OperationType,
        city: str,
        **filters,
    ) -> AsyncIterator[str]:
        """Get property URLs from listing pages."""
        page = 1
        max_pages = filters.pop("max_pages", 10)

        while page <= max_pages:
            url = self._build_search_url(operation_type, city, page, **filters)

            try:
                response = await self._fetch(url)
                soup = BeautifulSoup(response.text, "lxml")

                # Find property links (adapt selector to actual portal)
                property_links = soup.select("article.property-card a.property-link")

                if not property_links:
                    break

                for link in property_links:
                    href = link.get("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"{self.base_url}{href}"
                        yield href

                # Check if there's a next page
                next_page = soup.select_one("a.pagination-next")
                if not next_page:
                    break

                page += 1

            except Exception as e:
                break

    async def scrape_property(self, url: str) -> Optional[ScraperResult]:
        """Scrape a single property detail page."""
        try:
            response = await self._fetch(url)
            soup = BeautifulSoup(response.text, "lxml")

            # Extract data (adapt selectors to actual portal structure)
            title = self._extract_title(soup)
            price = self._extract_price(soup)
            city = self._extract_city(soup)
            property_type = self._extract_property_type(soup)
            operation_type = self._extract_operation_type(url)

            if not all([title, price, city]):
                return None

            return ScraperResult(
                source_url=url,
                external_id=self._extract_external_id(soup, url),
                title=title,
                description=self._extract_description(soup),
                price=price,
                city=city,
                property_type=property_type,
                operation_type=operation_type,
                address=self._extract_address(soup),
                neighborhood=self._extract_neighborhood(soup),
                province=self._extract_province(soup),
                postal_code=self._extract_postal_code(soup),
                latitude=self._extract_latitude(soup),
                longitude=self._extract_longitude(soup),
                area_built=self._extract_area(soup),
                bedrooms=self._extract_bedrooms(soup),
                bathrooms=self._extract_bathrooms(soup),
                floor=self._extract_floor(soup),
                has_elevator=self._extract_feature(soup, "ascensor"),
                has_parking=self._extract_feature(soup, "garaje"),
                has_terrace=self._extract_feature(soup, "terraza"),
                has_pool=self._extract_feature(soup, "piscina"),
                has_air_conditioning=self._extract_feature(soup, "aire acondicionado"),
                energy_rating=self._extract_energy_rating(soup),
                images=self._extract_images(soup),
                features=self._extract_features(soup),
                raw_data={"html_title": soup.title.string if soup.title else None},
            )

        except Exception as e:
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property title."""
        title_el = soup.select_one("h1.property-title")
        return title_el.get_text(strip=True) if title_el else None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract property price."""
        price_el = soup.select_one(".property-price")
        if price_el:
            price_text = price_el.get_text(strip=True)
            # Remove currency symbols and thousands separators
            price_clean = re.sub(r"[^\d]", "", price_text)
            if price_clean:
                return Decimal(price_clean)
        return None

    def _extract_city(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract city name."""
        location_el = soup.select_one(".property-location")
        if location_el:
            # Parse location text to extract city
            location_text = location_el.get_text(strip=True)
            parts = location_text.split(",")
            if len(parts) >= 2:
                return parts[-2].strip()
        return None

    def _extract_property_type(self, soup: BeautifulSoup) -> PropertyType:
        """Extract and map property type."""
        type_el = soup.select_one(".property-type")
        if type_el:
            type_text = type_el.get_text(strip=True).lower()
            for key, value in self.PROPERTY_TYPE_MAP.items():
                if key in type_text:
                    return value
        return PropertyType.OTHER

    def _extract_operation_type(self, url: str) -> OperationType:
        """Determine operation type from URL."""
        if "alquiler" in url.lower():
            return OperationType.RENT
        return OperationType.SALE

    def _extract_external_id(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """Extract external property ID."""
        # Try to find in page or extract from URL
        id_match = re.search(r"/(\d+)/?$", url)
        return id_match.group(1) if id_match else None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property description."""
        desc_el = soup.select_one(".property-description")
        return desc_el.get_text(strip=True) if desc_el else None

    def _extract_address(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract street address."""
        addr_el = soup.select_one(".property-address")
        return addr_el.get_text(strip=True) if addr_el else None

    def _extract_neighborhood(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract neighborhood name."""
        hood_el = soup.select_one(".property-neighborhood")
        return hood_el.get_text(strip=True) if hood_el else None

    def _extract_province(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract province name."""
        prov_el = soup.select_one(".property-province")
        return prov_el.get_text(strip=True) if prov_el else None

    def _extract_postal_code(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract postal code."""
        pc_el = soup.select_one(".property-postal-code")
        return pc_el.get_text(strip=True) if pc_el else None

    def _extract_latitude(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract latitude from map or data attributes."""
        map_el = soup.select_one("[data-lat]")
        if map_el:
            lat = map_el.get("data-lat")
            if lat:
                return Decimal(lat)
        return None

    def _extract_longitude(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract longitude from map or data attributes."""
        map_el = soup.select_one("[data-lng]")
        if map_el:
            lng = map_el.get("data-lng")
            if lng:
                return Decimal(lng)
        return None

    def _extract_area(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract built area in square meters."""
        area_el = soup.select_one(".property-area")
        if area_el:
            area_text = area_el.get_text(strip=True)
            area_match = re.search(r"(\d+)", area_text)
            if area_match:
                return Decimal(area_match.group(1))
        return None

    def _extract_bedrooms(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract number of bedrooms."""
        beds_el = soup.select_one(".property-bedrooms")
        if beds_el:
            beds_text = beds_el.get_text(strip=True)
            beds_match = re.search(r"(\d+)", beds_text)
            if beds_match:
                return int(beds_match.group(1))
        return None

    def _extract_bathrooms(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract number of bathrooms."""
        baths_el = soup.select_one(".property-bathrooms")
        if baths_el:
            baths_text = baths_el.get_text(strip=True)
            baths_match = re.search(r"(\d+)", baths_text)
            if baths_match:
                return int(baths_match.group(1))
        return None

    def _extract_floor(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract floor number."""
        floor_el = soup.select_one(".property-floor")
        if floor_el:
            floor_text = floor_el.get_text(strip=True).lower()
            if "bajo" in floor_text:
                return 0
            floor_match = re.search(r"(\d+)", floor_text)
            if floor_match:
                return int(floor_match.group(1))
        return None

    def _extract_feature(self, soup: BeautifulSoup, feature_name: str) -> Optional[bool]:
        """Check if a feature is present."""
        features_el = soup.select(".property-feature")
        for el in features_el:
            if feature_name.lower() in el.get_text(strip=True).lower():
                return True
        return None

    def _extract_energy_rating(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract energy efficiency rating."""
        energy_el = soup.select_one(".energy-rating")
        if energy_el:
            rating_text = energy_el.get_text(strip=True).upper()
            if rating_text in "ABCDEFG":
                return rating_text
        return None

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        """Extract image URLs."""
        images = []
        img_els = soup.select(".property-gallery img")
        for img in img_els:
            src = img.get("src") or img.get("data-src")
            if src:
                if not src.startswith("http"):
                    src = f"{self.base_url}{src}"
                images.append(src)
        return images

    def _extract_features(self, soup: BeautifulSoup) -> list[str]:
        """Extract list of property features."""
        features = []
        feature_els = soup.select(".property-feature")
        for el in feature_els:
            text = el.get_text(strip=True)
            if text:
                features.append(text)
        return features
