"""Tests for the Inmuebles24 scraper."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

from app.services.scrapers.inmuebles24 import Inmuebles24Scraper, PlaywrightFetcher
from app.models.property import PropertyType, OperationType


# Sample HTML responses for testing
SAMPLE_LISTING_HTML = """
<!DOCTYPE html>
<html>
<head><title>Departamentos en Venta en Condesa</title></head>
<body>
    <div data-qa="posting" class="postingCard">
        <a data-qa="posting-title" href="/propiedades/departamento-en-venta-condesa-12345678.html">
            Departamento en Condesa
        </a>
    </div>
    <div data-qa="posting" class="postingCard">
        <a data-qa="posting-title" href="/propiedades/departamento-en-venta-condesa-87654321.html">
            Otro Departamento en Condesa
        </a>
    </div>
    <a data-qa="pagination-next" href="/departamentos-en-venta-en-condesa-pagina-2.html">
        Siguiente
    </a>
</body>
</html>
"""

SAMPLE_PROPERTY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Departamento en Venta en Condesa | Inmuebles24</title>
    <script type="application/ld+json">
    {
        "@type": "RealEstateListing",
        "name": "Hermoso departamento en Condesa",
        "offers": {
            "price": 5500000,
            "priceCurrency": "MXN"
        },
        "geo": {
            "latitude": 19.4117,
            "longitude": -99.1748
        },
        "image": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
    }
    </script>
</head>
<body>
    <h1 data-qa="posting-title">Hermoso departamento en Condesa</h1>
    <div data-qa="posting-price">$5,500,000 MXN</div>
    <div data-qa="posting-location">Condesa, Cuauhtémoc, Ciudad de México</div>
    <div data-qa="posting-area">120 m²</div>
    <div data-qa="posting-bedrooms">3 recámaras</div>
    <div data-qa="posting-bathrooms">2 baños</div>
    <div data-qa="posting-description">
        Hermoso departamento con excelente ubicación en la Condesa.
        Cuenta con 3 recámaras, 2 baños completos, sala-comedor amplio,
        cocina integral y 2 lugares de estacionamiento.
    </div>
    <div class="property-features">
        <div data-qa="posting-feature">Estacionamiento</div>
        <div data-qa="posting-feature">Elevador</div>
        <div data-qa="posting-feature">Gimnasio</div>
        <div data-qa="posting-feature">Roof Garden</div>
    </div>
    <div data-qa="gallery-img">
        <img src="https://example.com/img1.jpg" />
    </div>
    <div data-qa="gallery-img">
        <img src="https://example.com/img2.jpg" />
    </div>
</body>
</html>
"""

SAMPLE_PROPERTY_HTML_MINIMAL = """
<!DOCTYPE html>
<html>
<body>
    <h1>Departamento en Roma Norte</h1>
    <span class="price">$3,200,000</span>
    <span class="location">Roma Norte, Ciudad de México</span>
    <span title="85 m²">85 m²</span>
    <span title="2 recámaras">2 recámaras</span>
    <span title="1 baño">1 baño</span>
</body>
</html>
"""


class TestInmuebles24Scraper:
    """Test suite for Inmuebles24Scraper."""

    def test_normalize_colonia(self):
        """Test colonia name normalization."""
        scraper = Inmuebles24Scraper()

        assert scraper._normalize_colonia("condesa") == "condesa"
        assert scraper._normalize_colonia("roma norte") == "roma-norte"
        assert scraper._normalize_colonia("Roma Norte") == "roma-norte"
        assert scraper._normalize_colonia("POLANCO") == "polanco"
        assert scraper._normalize_colonia("del valle") == "del-valle"
        assert scraper._normalize_colonia("lomas de chapultepec") == "lomas-de-chapultepec"

    def test_build_search_url_sale(self):
        """Test search URL building for sales."""
        scraper = Inmuebles24Scraper()

        url = scraper._build_search_url(
            operation_type=OperationType.SALE,
            colonia="condesa",
            page=1,
        )

        assert "inmuebles24.com" in url
        assert "venta" in url
        assert "condesa" in url
        assert ".html" in url

    def test_build_search_url_rent(self):
        """Test search URL building for rentals."""
        scraper = Inmuebles24Scraper()

        url = scraper._build_search_url(
            operation_type=OperationType.RENT,
            colonia="roma-norte",
            page=1,
        )

        assert "renta" in url
        assert "roma-norte" in url

    def test_build_search_url_with_filters(self):
        """Test search URL building with filters."""
        scraper = Inmuebles24Scraper()

        url = scraper._build_search_url(
            operation_type=OperationType.SALE,
            colonia="polanco",
            page=2,
            price_min=3000000,
            price_max=10000000,
            bedrooms_min=2,
        )

        assert "polanco" in url
        assert "precio-desde-3000000" in url
        assert "precio-hasta-10000000" in url
        assert "2-recamaras" in url
        assert "pagina-2" in url

    def test_extract_listing_urls(self):
        """Test extraction of property URLs from listing page."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_LISTING_HTML, "lxml")

        urls = scraper._extract_listing_urls(soup)

        assert len(urls) == 2
        assert all("/propiedades/" in url for url in urls)
        assert "12345678" in urls[0]
        assert "87654321" in urls[1]

    def test_has_next_page(self):
        """Test detection of pagination next link."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_LISTING_HTML, "lxml")

        assert scraper._has_next_page(soup) is True

        # Test without next page
        soup_no_next = BeautifulSoup("<html><body></body></html>", "lxml")
        assert scraper._has_next_page(soup_no_next) is False

    def test_extract_external_id(self):
        """Test external ID extraction from URL."""
        scraper = Inmuebles24Scraper()

        url = "https://www.inmuebles24.com/propiedades/departamento-en-venta-12345678.html"
        assert scraper._extract_external_id(url) == "12345678"

        url2 = "https://www.inmuebles24.com/propiedades/casa-87654321.html"
        assert scraper._extract_external_id(url2) == "87654321"

    def test_extract_title(self):
        """Test title extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        title = scraper._extract_title(soup)
        assert title == "Hermoso departamento en Condesa"

    def test_extract_price(self):
        """Test price extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        price = scraper._extract_price(soup)
        assert price == Decimal("5500000")

    def test_parse_price_formats(self):
        """Test various price format parsing."""
        scraper = Inmuebles24Scraper()

        assert scraper._parse_price("$5,500,000 MXN") == Decimal("5500000")
        assert scraper._parse_price("5500000") == Decimal("5500000")
        assert scraper._parse_price("$3.200.000") == Decimal("3200000")
        assert scraper._parse_price("MXN 1,234,567.00") == Decimal("1234567")
        assert scraper._parse_price("") is None
        assert scraper._parse_price(None) is None

    def test_extract_location(self):
        """Test location extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        address, neighborhood, city = scraper._extract_location(soup)

        assert neighborhood == "Condesa"
        assert "México" in city or city == "Ciudad de México"

    def test_extract_area(self):
        """Test area extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        area = scraper._extract_area(soup)
        assert area == Decimal("120")

    def test_extract_bedrooms(self):
        """Test bedroom count extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        bedrooms = scraper._extract_bedrooms(soup)
        assert bedrooms == 3

    def test_extract_bathrooms(self):
        """Test bathroom count extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        bathrooms = scraper._extract_bathrooms(soup)
        assert bathrooms == 2

    def test_extract_property_type_from_url(self):
        """Test property type extraction from URL."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        url = "https://www.inmuebles24.com/propiedades/departamento-en-venta-12345.html"
        prop_type = scraper._extract_property_type(soup, url)
        assert prop_type == PropertyType.APARTMENT

        url2 = "https://www.inmuebles24.com/propiedades/casa-en-venta-12345.html"
        prop_type2 = scraper._extract_property_type(soup, url2)
        assert prop_type2 == PropertyType.HOUSE

    def test_extract_operation_type(self):
        """Test operation type extraction from URL."""
        scraper = Inmuebles24Scraper()

        assert scraper._extract_operation_type(
            "https://example.com/departamento-en-venta.html"
        ) == OperationType.SALE

        assert scraper._extract_operation_type(
            "https://example.com/departamento-en-renta.html"
        ) == OperationType.RENT

    def test_extract_description(self):
        """Test description extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        description = scraper._extract_description(soup)
        assert description is not None
        assert "Condesa" in description
        assert "estacionamiento" in description.lower()

    def test_extract_images(self):
        """Test image URL extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        images = scraper._extract_images(soup)
        assert len(images) >= 2
        assert all("example.com" in img for img in images)

    def test_extract_features(self):
        """Test feature list extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        features = scraper._extract_features(soup)
        assert "Estacionamiento" in features
        assert "Elevador" in features
        assert "Gimnasio" in features

    def test_extract_coordinates_from_json_ld(self):
        """Test coordinate extraction from JSON-LD."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        lat, lng = scraper._extract_coordinates(soup)
        assert lat == Decimal("19.4117")
        assert lng == Decimal("-99.1748")

    def test_extract_parking(self):
        """Test parking information extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        parking = scraper._extract_parking(soup)
        assert parking["has_parking"] is True

    def test_extract_amenities(self):
        """Test amenities extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        amenities = scraper._extract_amenities(soup)
        assert amenities["elevator"] is True
        assert amenities["gym"] is True

    def test_extract_json_ld(self):
        """Test JSON-LD structured data extraction."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        json_ld = scraper._extract_json_ld(soup)
        assert json_ld is not None
        assert json_ld["@type"] == "RealEstateListing"
        assert json_ld["offers"]["price"] == 5500000

    def test_is_valid_response(self):
        """Test response validation."""
        scraper = Inmuebles24Scraper()

        assert scraper._is_valid_response(SAMPLE_PROPERTY_HTML) is True
        assert scraper._is_valid_response("") is False
        assert scraper._is_valid_response(None) is False
        assert scraper._is_valid_response("Access Denied - Robot detected") is False

    def test_parse_property_page_full(self):
        """Test full property page parsing."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML, "lxml")

        result = scraper._parse_property_page(
            soup,
            "https://www.inmuebles24.com/propiedades/departamento-12345678.html"
        )

        assert result is not None
        assert result.title == "Hermoso departamento en Condesa"
        assert result.price == Decimal("5500000")
        assert result.price_currency == "MXN"
        assert result.bedrooms == 3
        assert result.bathrooms == 2
        assert result.area_built == Decimal("120")
        assert result.neighborhood == "Condesa"
        assert result.property_type == PropertyType.APARTMENT
        assert len(result.images) >= 2
        assert result.latitude is not None
        assert result.longitude is not None

    def test_parse_property_page_minimal(self):
        """Test property page parsing with minimal data."""
        scraper = Inmuebles24Scraper()
        soup = BeautifulSoup(SAMPLE_PROPERTY_HTML_MINIMAL, "lxml")

        result = scraper._parse_property_page(
            soup,
            "https://www.inmuebles24.com/propiedades/departamento-99999999.html"
        )

        # With minimal HTML, parsing should still attempt to find data
        # but may not find all fields
        assert result is not None
        assert result.title is not None


class TestPlaywrightFetcher:
    """Test suite for PlaywrightFetcher."""

    @pytest.mark.asyncio
    async def test_setup_without_playwright(self):
        """Test that setup handles missing Playwright gracefully."""
        fetcher = PlaywrightFetcher()

        with patch.dict("sys.modules", {"playwright": None}):
            await fetcher.setup()
            # Should not raise, browser should be None
            assert fetcher._browser is None

        await fetcher.teardown()

    @pytest.mark.asyncio
    async def test_fetch_without_browser(self):
        """Test fetch returns None when browser not initialized."""
        fetcher = PlaywrightFetcher()
        # Don't call setup, browser should be None

        result = await fetcher.fetch("https://example.com")
        assert result is None


class TestInmuebles24Integration:
    """Integration tests for Inmuebles24 scraper (require network)."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test - requires network")
    async def test_scrape_real_listing(self):
        """Test scraping a real listing page."""
        async with Inmuebles24Scraper({"use_playwright": False}) as scraper:
            urls = []
            async for url in scraper.get_listing_urls(
                operation_type=OperationType.SALE,
                city="condesa",
                max_pages=1,
            ):
                urls.append(url)
                if len(urls) >= 3:
                    break

            assert len(urls) > 0
            assert all("/propiedades/" in url for url in urls)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test - requires network")
    async def test_scrape_real_property(self):
        """Test scraping a real property page."""
        async with Inmuebles24Scraper({"use_playwright": False}) as scraper:
            # First get a real URL
            urls = []
            async for url in scraper.get_listing_urls(
                operation_type=OperationType.SALE,
                city="condesa",
                max_pages=1,
            ):
                urls.append(url)
                break

            if urls:
                result = await scraper.scrape_property(urls[0])
                assert result is not None
                assert result.title is not None
                assert result.price is not None
                assert result.city is not None
