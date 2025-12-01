"""Deduplication service for property matching."""

from app.services.deduplication.service import DeduplicationService
from app.services.deduplication.normalizer import AddressNormalizer

__all__ = ["DeduplicationService", "AddressNormalizer"]
