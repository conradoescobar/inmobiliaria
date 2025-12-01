#!/usr/bin/env python3
"""
DEMO: Cómo usar el scraper de Inmuebles24

Este script muestra el uso del scraper. En un entorno con acceso a internet,
produciría resultados reales.
"""

# ============================================================================
# OPCIÓN 1: Usar la API REST
# ============================================================================
"""
# Iniciar el servidor:
uvicorn app.main:app --reload

# Llamar al endpoint de scraping:
curl -X POST "http://localhost:8000/api/v1/scraping/inmuebles24/start" \\
     -H "Content-Type: application/json" \\
     -d '{
       "colonias": ["condesa", "roma norte"],
       "operation_type": "sale",
       "bedrooms_min": 3,
       "max_properties": 50,
       "max_pages": 5,
       "price_min": 3000000,
       "price_max": 15000000
     }'

# Respuesta:
{
  "id": 1,
  "source_id": 1,
  "status": "pending",
  "properties_found": 0,
  ...
}

# Verificar el estado:
curl "http://localhost:8000/api/v1/scraping/runs/1"

# Ver colonias disponibles:
curl "http://localhost:8000/api/v1/scraping/colonias"
"""

# ============================================================================
# OPCIÓN 2: Usar el scraper directamente en código
# ============================================================================

EXAMPLE_CODE = '''
import asyncio
from app.services.scrapers import Inmuebles24Scraper
from app.models.property import OperationType

async def buscar_depas_condesa():
    """Buscar departamentos en la Condesa."""

    config = {
        "use_playwright": True,  # Mejor para evitar bloqueos
    }

    async with Inmuebles24Scraper(config) as scraper:
        async for propiedad in scraper.scrape_listings(
            operation_type=OperationType.SALE,
            city="ciudad-de-mexico",
            colonias=["condesa", "roma norte", "polanco"],
            bedrooms_min=3,
            price_min=3000000,
            price_max=15000000,
            max_pages=10,
        ):
            print(f"🏠 {propiedad.title}")
            print(f"   💰 ${propiedad.price:,.0f} MXN")
            print(f"   📐 {propiedad.area_built} m²")
            print(f"   🛏️  {propiedad.bedrooms} recámaras, {propiedad.bathrooms} baños")
            print(f"   📍 {propiedad.neighborhood}")
            print(f"   🔗 {propiedad.source_url}")
            print()

# Ejecutar
asyncio.run(buscar_depas_condesa())
'''

# ============================================================================
# OPCIÓN 3: Con guardado en PostgreSQL y deduplicación
# ============================================================================

EXAMPLE_WITH_DB = '''
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.services.scrapers import Inmuebles24Scraper
from app.services.deduplication import DeduplicationService
from app.services.property_service import PropertyService
from app.models.property import OperationType, ScrapingSource

async def scrape_con_guardado():
    """Scraping con guardado automático en BD."""

    async with AsyncSessionLocal() as db:
        # Obtener o crear la fuente
        source = ScrapingSource(
            name="inmuebles24",
            base_url="https://www.inmuebles24.com",
            scraper_class="inmuebles24",
        )

        # Servicios
        dedup = DeduplicationService(db)
        props = PropertyService(db)

        stats = {"new": 0, "updated": 0, "duplicates": 0}

        async with Inmuebles24Scraper() as scraper:
            async for result in scraper.scrape_listings(
                operation_type=OperationType.SALE,
                city="cdmx",
                colonias=["condesa"],
                bedrooms_min=3,
            ):
                # Verificar duplicados
                is_dup, dup_id = await dedup.check_duplicate(result)

                if is_dup:
                    stats["duplicates"] += 1
                    continue

                # Verificar si ya existe por URL
                existing = await props.get_by_url(result.source_url)

                if existing:
                    await props.update_from_scraper(existing.id, result)
                    stats["updated"] += 1
                else:
                    await props.create_from_scraper(result, source.id)
                    stats["new"] += 1

        print(f"✅ Resultados:")
        print(f"   Nuevas: {stats['new']}")
        print(f"   Actualizadas: {stats['updated']}")
        print(f"   Duplicadas: {stats['duplicates']}")

asyncio.run(scrape_con_guardado())
'''

# ============================================================================
# DATOS DE EJEMPLO (lo que devolvería el scraper)
# ============================================================================

SAMPLE_RESULTS = [
    {
        "title": "Departamento en venta en Condesa, Cuauhtémoc",
        "price": 8500000,
        "price_currency": "MXN",
        "area_built": 145,
        "bedrooms": 3,
        "bathrooms": 2,
        "neighborhood": "Condesa",
        "city": "Ciudad de México",
        "source_url": "https://www.inmuebles24.com/propiedades/depto-condesa-12345678.html",
        "features": ["Estacionamiento", "Elevador", "Roof Garden", "Gimnasio"],
        "images": 15,
    },
    {
        "title": "Amplio depto renovado en Condesa con terraza",
        "price": 12000000,
        "price_currency": "MXN",
        "area_built": 180,
        "bedrooms": 3,
        "bathrooms": 3,
        "neighborhood": "Condesa",
        "city": "Ciudad de México",
        "source_url": "https://www.inmuebles24.com/propiedades/depto-terraza-87654321.html",
        "features": ["Terraza privada", "2 estacionamientos", "Bodega", "Vigilancia 24h"],
        "images": 22,
    },
    {
        "title": "Penthouse en venta Condesa con vista al parque",
        "price": 18500000,
        "price_currency": "MXN",
        "area_built": 250,
        "bedrooms": 4,
        "bathrooms": 4,
        "neighborhood": "Hipódromo Condesa",
        "city": "Ciudad de México",
        "source_url": "https://www.inmuebles24.com/propiedades/penthouse-condesa-11223344.html",
        "features": ["Doble altura", "Terraza 80m²", "3 estacionamientos", "Alberca"],
        "images": 35,
    },
]


def main():
    """Mostrar demo de resultados esperados."""
    print("=" * 70)
    print("🏠 DEMO: Resultados esperados del scraper Inmuebles24")
    print("   Búsqueda: Departamentos en venta en Condesa, 3+ recámaras")
    print("=" * 70)
    print()

    for i, prop in enumerate(SAMPLE_RESULTS, 1):
        print(f"{'─' * 70}")
        print(f"🏢 Propiedad #{i}: {prop['title']}")
        print(f"{'─' * 70}")
        print(f"   💰 Precio: ${prop['price']:,} {prop['price_currency']}")
        print(f"   📐 Área: {prop['area_built']} m²")
        print(f"   📊 Precio/m²: ${prop['price'] // prop['area_built']:,} MXN")
        print(f"   🛏️  Recámaras: {prop['bedrooms']}")
        print(f"   🚿 Baños: {prop['bathrooms']}")
        print(f"   📍 Colonia: {prop['neighborhood']}, {prop['city']}")
        print(f"   🖼️  Fotos: {prop['images']}")
        print(f"   ✨ Amenidades: {', '.join(prop['features'][:4])}")
        print(f"   🔗 URL: {prop['source_url']}")
        print()

    print("=" * 70)
    print("📝 PARA EJECUTAR EN PRODUCCIÓN:")
    print("=" * 70)
    print("""
1. Asegúrate de tener acceso a internet desde tu servidor

2. Instala las dependencias:
   pip install -r requirements.txt
   playwright install chromium

3. Configura PostgreSQL con PostGIS:
   docker-compose up -d db

4. Aplica las migraciones:
   alembic upgrade head

5. Inicia el servidor:
   uvicorn app.main:app --reload

6. Usa el endpoint:
   POST http://localhost:8000/api/v1/scraping/inmuebles24/start
   {
     "colonias": ["condesa"],
     "operation_type": "sale",
     "bedrooms_min": 3
   }
""")


if __name__ == "__main__":
    main()
