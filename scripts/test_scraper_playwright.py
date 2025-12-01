#!/usr/bin/env python3
"""Script de prueba con Playwright para evitar bloqueos."""

import asyncio
import re
import json
from decimal import Decimal
from typing import Optional, List


async def main():
    """Buscar departamentos en Condesa con Playwright."""
    print("=" * 70)
    print("🏠 PRUEBA: Scraper Inmuebles24 (con Playwright)")
    print("   Búsqueda: Departamentos en venta en Condesa, 3+ recámaras")
    print("=" * 70)
    print()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright no está instalado. Ejecuta:")
        print("   pip install playwright && playwright install chromium")
        return

    url = "https://www.inmuebles24.com/departamentos-en-venta-en-condesa-con-3-recamaras.html"

    print(f"📡 URL: {url}")
    print("⏳ Iniciando navegador...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = await browser.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Agregar headers realistas
        await page.set_extra_http_headers({
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        })

        print("🌐 Navegando a la página...")

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Esperar un poco para que cargue el contenido dinámico
            await asyncio.sleep(3)

            # Capturar screenshot para debug
            await page.screenshot(path="/tmp/inmuebles24_test.png")
            print("📸 Screenshot guardado en /tmp/inmuebles24_test.png")

            # Obtener el contenido
            content = await page.content()

            # Buscar propiedades
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")

            # Buscar cards de propiedades
            property_cards = (
                soup.select("[data-qa='posting']") or
                soup.select(".postingCard") or
                soup.select("div[data-posting-type]") or
                soup.select("article.posting")
            )

            print(f"\n📋 Cards de propiedades encontrados: {len(property_cards)}")

            # Si no encontramos cards, buscar links a propiedades
            if not property_cards:
                prop_links = [a for a in soup.find_all("a", href=True)
                             if "/propiedades/" in a.get("href", "")]
                print(f"🔗 Links a propiedades encontrados: {len(prop_links)}")

                if prop_links:
                    # Visitar la primera propiedad
                    first_link = prop_links[0]["href"]
                    if not first_link.startswith("http"):
                        first_link = f"https://www.inmuebles24.com{first_link}"

                    print(f"\n⏳ Visitando primera propiedad: {first_link[:60]}...")
                    await page.goto(first_link, wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(2)

                    prop_content = await page.content()
                    prop_soup = BeautifulSoup(prop_content, "lxml")

                    # Extraer datos
                    title_el = (
                        prop_soup.select_one("h1[data-qa='posting-title']") or
                        prop_soup.select_one("h1.posting-title") or
                        prop_soup.select_one("h1")
                    )

                    price_el = (
                        prop_soup.select_one("[data-qa='posting-price']") or
                        prop_soup.select_one(".posting-price") or
                        prop_soup.select_one(".price")
                    )

                    location_el = (
                        prop_soup.select_one("[data-qa='posting-location']") or
                        prop_soup.select_one(".posting-location")
                    )

                    if title_el:
                        print(f"\n{'─' * 70}")
                        print(f"🏢 {title_el.get_text(strip=True)}")
                        print(f"{'─' * 70}")

                    if price_el:
                        price_text = price_el.get_text(strip=True)
                        print(f"   💰 Precio: {price_text}")

                    if location_el:
                        print(f"   📍 Ubicación: {location_el.get_text(strip=True)}")

                    # Buscar características
                    for sel in ["[data-qa='posting-area']", "[data-qa='posting-bedrooms']", "[data-qa='posting-bathrooms']"]:
                        el = prop_soup.select_one(sel)
                        if el:
                            print(f"   ✓ {el.get_text(strip=True)}")

                    # Imágenes
                    images = prop_soup.select("[data-qa='gallery-img'] img, .gallery-image img")
                    print(f"   🖼️  Fotos: {len(images)}")

                    print(f"   🔗 URL: {first_link}")

            else:
                # Procesar los cards encontrados
                print("\n📊 Primeras 5 propiedades encontradas:\n")

                for i, card in enumerate(property_cards[:5], 1):
                    print(f"{'─' * 70}")
                    print(f"🏢 Propiedad #{i}")

                    # Título
                    title = card.select_one("[data-qa='posting-title'], .posting-title, h2, h3")
                    if title:
                        print(f"   Título: {title.get_text(strip=True)[:60]}...")

                    # Precio
                    price = card.select_one("[data-qa='posting-price'], .posting-price, .price")
                    if price:
                        print(f"   Precio: {price.get_text(strip=True)}")

                    # Ubicación
                    loc = card.select_one("[data-qa='posting-location'], .posting-location")
                    if loc:
                        print(f"   Ubicación: {loc.get_text(strip=True)}")

                    # Link
                    link = card.select_one("a[href*='/propiedades/']")
                    if link:
                        href = link.get("href")
                        if not href.startswith("http"):
                            href = f"https://www.inmuebles24.com{href}"
                        print(f"   URL: {href[:70]}...")

                    print()

        except Exception as e:
            print(f"❌ Error: {e}")

            # Intentar capturar el contenido actual para debug
            try:
                content = await page.content()
                print(f"\n📄 Contenido parcial ({len(content)} bytes):")

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, "lxml")
                title = soup.title.string if soup.title else "Sin título"
                print(f"   Título de página: {title}")

                # Verificar si hay mensaje de error o captcha
                if "captcha" in content.lower():
                    print("   ⚠️ Se detectó un CAPTCHA")
                if "blocked" in content.lower() or "denied" in content.lower():
                    print("   ⚠️ Acceso bloqueado")

            except Exception as e2:
                print(f"   Error capturando contenido: {e2}")

        finally:
            await browser.close()

    print("\n" + "=" * 70)
    print("✓ Prueba completada")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
