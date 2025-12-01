"""Application configuration settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Inmobiliaria Aggregator"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/inmobiliaria"
    database_url_sync: str = "postgresql://postgres:password@localhost:5432/inmobiliaria"

    # Scraper settings
    scraper_user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    scraper_delay_seconds: float = 2.0
    scraper_max_retries: int = 3

    # Deduplication settings
    dedup_address_threshold: float = 0.85
    dedup_features_threshold: float = 0.90

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
