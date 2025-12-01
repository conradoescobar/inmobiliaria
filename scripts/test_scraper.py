#!/usr/bin/env python3
"""Script de prueba para el scraper de Inmuebles24."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal
from app.services.scrapers.inmuebles24 import Inmuebles24Scraper
from app.models.property import OperationType


async def main():
    """Buscar departamentos en Condesa con 3 recámaras."""
    print("=" * 60)
    print("🏠 Buscando departamentos en venta en Condesa")
    print("   Filtros: 3+ recámaras")
    print("=" * 60)
    print()

    config = {
        "use_playwright": False,  # Solo httpx para prueba rápida
    }

    properties_found = []

    try:
        async with Inmuebles24Scraper(config) as scraper:
            print("✓ Scraper inicializado")
            print("⏳ Buscando propiedades...\n")

            count = 0
            async for prop in scraper.scrape_listings(
                operation_type=OperationType.SALE,
                city="ciudad-de-mexico",
                colonias=["condesa"],
                bedrooms_min=3,
                max_pages=2,  # Limitar a 2 páginas para prueba
            ):
                count += 1
                properties_found.append(prop)

                print(f"📍 Propiedad #{count}")
                print(f"   Título: {prop.title[:60]}...")
                print(f"   Precio: ${prop.price:,.0f} MXN")

                if prop.area_built:
                    print(f"   Área: {prop.area_built} m²")
                    if prop.price:
                        price_per_m2 = prop.price / prop.area_built
                        print(f"   Precio/m²: ${price_per_m2:,.0f} MXN")

                if prop.bedrooms:
                    print(f"   Recámaras: {prop.bedrooms}")
                if prop.bathrooms:
                    print(f"   Baños: {prop.bathrooms}")
                if prop.neighborhood:
                    print(f"   Colonia: {prop.neighborhood}")
                if prop.address:
                    print(f"   Dirección: {prop.address}")

                print(f"   URL: {prop.source_url}")

                if prop.images:
                    print(f"   Imágenes: {len(prop.images)} fotos")

                if prop.features:
                    print(f"   Amenidades: {', '.join(prop.features[:5])}")

                print()

                # Limitar a 5 propiedades para la prueba
                if count >= 5:
                    print("(Limitado a 5 propiedades para prueba)")
                    break

            # Estadísticas del scraper
            stats = scraper.get_stats()
            print("=" * 60)
            print("📊 Estadísticas del scraper:")
            print(f"   Requests realizados: {stats['request_count']}")
            print(f"   URLs fallidos: {stats.get('failed_urls', 0)}")
            print(f"   Propiedades encontradas: {count}")
            print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    if not properties_found:
        print("⚠️  No se encontraron propiedades. Posibles razones:")
        print("   - El sitio puede estar bloqueando requests")
        print("   - La estructura HTML puede haber cambiado")
        print("   - Intenta con use_playwright=True")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
