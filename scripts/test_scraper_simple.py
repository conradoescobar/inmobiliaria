#!/usr/bin/env python3
"""Script simple para probar el scraper de Inmuebles24 sin dependencias de DB."""

import asyncio
import re
import json
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime
from urllib.parse import urljoin
from enum import Enum

import httpx
from bs4 import BeautifulSoup


class OperationType(str, Enum):
    SALE = "sale"
    RENT = "rent"


class PropertyType(str, Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    OTHER = "other"


@dataclass
class ScraperResult:
    """Resultado del scraping."""
    source_url: str
    title: str
    price: Decimal
    city: str
    property_type: PropertyType
    operation_type: OperationType
    external_id: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    area_built: Optional[Decimal] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    images: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)


class Inmuebles24ScraperSimple:
    """Scraper simplificado para Inmuebles24."""

    BASE_URL = "https://www.inmuebles24.com"

    CDMX_COLONIAS = {
        "condesa": "condesa",
        "roma norte": "roma-norte",
        "polanco": "polanco",
        "del valle": "del-valle",
    }

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._request_count = 0

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _normalize_colonia(self, colonia: str) -> str:
        colonia_lower = colonia.lower().strip()
        if colonia_lower in self.CDMX_COLONIAS:
            return self.CDMX_COLONIAS[colonia_lower]
        return colonia_lower.replace(" ", "-")

    def _build_search_url(self, colonia: str, operation: str, page: int = 1, **filters) -> str:
        colonia_slug = self._normalize_colonia(colonia)
        op = "venta" if operation == "sale" else "renta"

        url = f"{self.BASE_URL}/departamentos-en-{op}-en-{colonia_slug}.html"

        params = []
        if filters.get("bedrooms_min"):
            params.append(f"con-{filters['bedrooms_min']}-recamaras")
        if page > 1:
            params.append(f"pagina-{page}")

        if params:
            url = url.replace(".html", f"-{'-'.join(params)}.html")

        return url

    async def _fetch(self, url: str) -> Optional[str]:
        try:
            await asyncio.sleep(2)  # Rate limiting
            response = await self._client.get(url)
            response.raise_for_status()
            self._request_count += 1
            return response.text
        except Exception as e:
            print(f"   ⚠️ Error fetching {url}: {e}")
            return None

    def _extract_listing_urls(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []

        # Múltiples selectores para diferentes estructuras
        selectors = [
            "a[data-qa='posting-title']",
            "div[data-qa='posting'] a[href*='/propiedades/']",
            "a.go-to-posting",
            "a[href*='/propiedades/']",
        ]

        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get("href")
                if href and "/propiedades/" in href:
                    if not href.startswith("http"):
                        href = urljoin(self.BASE_URL, href)
                    if href not in urls:
                        urls.append(href)

        return urls

    def _parse_price(self, text: str) -> Optional[Decimal]:
        if not text:
            return None
        clean = re.sub(r"[^\d.,]", "", text)
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", "")
        try:
            return Decimal(clean)
        except:
            return None

    def _parse_property(self, html: str, url: str) -> Optional[ScraperResult]:
        soup = BeautifulSoup(html, "lxml")

        # Título
        title = None
        for sel in ["h1[data-qa='posting-title']", "h1.posting-title", "h1"]:
            el = soup.select_one(sel)
            if el:
                title = el.get_text(strip=True)
                if title and len(title) > 5:
                    break

        if not title:
            return None

        # Precio
        price = None
        for sel in ["[data-qa='posting-price']", ".posting-price", ".price"]:
            el = soup.select_one(sel)
            if el:
                price = self._parse_price(el.get_text())
                if price:
                    break

        # Intentar JSON-LD
        if not price:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and "offers" in data:
                        price = Decimal(str(data["offers"].get("price", 0)))
                        break
                except:
                    pass

        if not price:
            return None

        # Ubicación
        neighborhood = None
        city = "Ciudad de México"
        for sel in ["[data-qa='posting-location']", ".posting-location", ".location"]:
            el = soup.select_one(sel)
            if el:
                loc = el.get_text(strip=True)
                parts = [p.strip() for p in loc.split(",")]
                if parts:
                    neighborhood = parts[0]
                break

        # Área
        area = None
        for sel in ["[data-qa='posting-area']", "span[title*='m²']"]:
            el = soup.select_one(sel)
            if el:
                match = re.search(r"(\d+)", el.get_text())
                if match:
                    area = Decimal(match.group(1))
                    break

        # También buscar en texto
        if not area:
            text = soup.get_text()
            match = re.search(r"(\d+)\s*m[²2]", text)
            if match:
                area = Decimal(match.group(1))

        # Recámaras
        bedrooms = None
        for sel in ["[data-qa='posting-bedrooms']", "span[title*='recámara']"]:
            el = soup.select_one(sel)
            if el:
                match = re.search(r"(\d+)", el.get_text())
                if match:
                    bedrooms = int(match.group(1))
                    break

        if not bedrooms:
            text = soup.get_text().lower()
            match = re.search(r"(\d+)\s*(?:recámara|habitacion|dormitorio)", text)
            if match:
                bedrooms = int(match.group(1))

        # Baños
        bathrooms = None
        for sel in ["[data-qa='posting-bathrooms']", "span[title*='baño']"]:
            el = soup.select_one(sel)
            if el:
                match = re.search(r"(\d+)", el.get_text())
                if match:
                    bathrooms = int(match.group(1))
                    break

        if not bathrooms:
            text = soup.get_text().lower()
            match = re.search(r"(\d+)\s*baño", text)
            if match:
                bathrooms = int(match.group(1))

        # Imágenes
        images = []
        for sel in ["[data-qa='gallery-img'] img", ".gallery-image img", "img[data-flickity-lazyload]"]:
            for img in soup.select(sel):
                src = img.get("src") or img.get("data-src") or img.get("data-flickity-lazyload")
                if src and "placeholder" not in src.lower():
                    if not src.startswith("http"):
                        src = urljoin(self.BASE_URL, src)
                    if src not in images:
                        images.append(src)

        # Features
        features = []
        for el in soup.select("[data-qa='posting-feature'], .posting-feature"):
            text = el.get_text(strip=True)
            if text:
                features.append(text)

        # External ID
        external_id = None
        match = re.search(r"-(\d+)\.html", url)
        if match:
            external_id = match.group(1)

        return ScraperResult(
            source_url=url,
            external_id=external_id,
            title=title,
            price=price,
            city=city,
            neighborhood=neighborhood,
            property_type=PropertyType.APARTMENT,
            operation_type=OperationType.SALE,
            area_built=area,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            images=images[:10],
            features=features,
        )

    async def search(
        self,
        colonia: str,
        operation: str = "sale",
        max_results: int = 5,
        **filters,
    ) -> AsyncIterator[ScraperResult]:
        """Buscar propiedades en una colonia."""
        print(f"   🔍 Buscando en {colonia}...")

        url = self._build_search_url(colonia, operation, **filters)
        print(f"   📡 URL: {url}")

        html = await self._fetch(url)
        if not html:
            return

        urls = self._extract_listing_urls(html)
        print(f"   📋 Encontradas {len(urls)} URLs de propiedades")

        count = 0
        for prop_url in urls[:max_results]:
            print(f"   ⏳ Procesando: {prop_url[:60]}...")

            prop_html = await self._fetch(prop_url)
            if not prop_html:
                continue

            result = self._parse_property(prop_html, prop_url)
            if result:
                count += 1
                yield result

        print(f"   ✓ Propiedades extraídas: {count}")


async def main():
    """Buscar departamentos en Condesa con 3 recámaras."""
    print("=" * 70)
    print("🏠 PRUEBA: Scraper Inmuebles24")
    print("   Búsqueda: Departamentos en venta en Condesa, 3+ recámaras")
    print("=" * 70)
    print()

    results = []

    async with Inmuebles24ScraperSimple() as scraper:
        async for prop in scraper.search(
            colonia="condesa",
            operation="sale",
            max_results=5,
            bedrooms_min=3,
        ):
            results.append(prop)

            print()
            print(f"{'─' * 70}")
            print(f"🏢 {prop.title}")
            print(f"{'─' * 70}")
            print(f"   💰 Precio: ${prop.price:,.0f} MXN")

            if prop.area_built:
                print(f"   📐 Área: {prop.area_built} m²")
                price_m2 = prop.price / prop.area_built
                print(f"   📊 Precio/m²: ${price_m2:,.0f} MXN")

            if prop.bedrooms:
                print(f"   🛏️  Recámaras: {prop.bedrooms}")
            if prop.bathrooms:
                print(f"   🚿 Baños: {prop.bathrooms}")
            if prop.neighborhood:
                print(f"   📍 Colonia: {prop.neighborhood}")

            print(f"   🔗 URL: {prop.source_url}")

            if prop.images:
                print(f"   🖼️  Fotos: {len(prop.images)}")

            if prop.features:
                print(f"   ✨ Amenidades: {', '.join(prop.features[:5])}")

    print()
    print("=" * 70)
    print(f"📊 RESUMEN: {len(results)} propiedades encontradas")
    print("=" * 70)

    if not results:
        print()
        print("⚠️  No se encontraron propiedades.")
        print("   Posibles causas:")
        print("   - El sitio puede bloquear requests automatizados")
        print("   - La estructura HTML pudo cambiar")


if __name__ == "__main__":
    asyncio.run(main())
