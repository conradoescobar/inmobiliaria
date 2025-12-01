"""Modular scraper system for real estate portals."""

from app.services.scrapers.base import BaseScraper, ScraperResult
from app.services.scrapers.manager import ScraperManager
from app.services.scrapers.inmuebles24 import Inmuebles24Scraper

__all__ = ["BaseScraper", "ScraperResult", "ScraperManager", "Inmuebles24Scraper"]
