"""Modular scraper system for real estate portals."""

from app.services.scrapers.base import BaseScraper, ScraperResult
from app.services.scrapers.manager import ScraperManager

__all__ = ["BaseScraper", "ScraperResult", "ScraperManager"]
