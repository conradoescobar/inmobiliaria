"""Deduplication service for identifying duplicate properties."""

import hashlib
import logging
from decimal import Decimal
from typing import Optional, Tuple, List

from rapidfuzz import fuzz
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.property import Property, PropertyStatus
from app.services.deduplication.normalizer import AddressNormalizer
from app.services.scrapers.base import ScraperResult

logger = logging.getLogger(__name__)
settings = get_settings()


class DeduplicationService:
    """
    Service for detecting duplicate property listings.

    Uses multiple signals to identify duplicates:
    - Normalized address similarity
    - Price similarity
    - Property characteristics (area, bedrooms, bathrooms)
    - Geographic proximity (if coordinates available)
    """

    def __init__(self, db: AsyncSession):
        """Initialize deduplication service."""
        self.db = db
        self.normalizer = AddressNormalizer()
        self.address_threshold = settings.dedup_address_threshold
        self.features_threshold = settings.dedup_features_threshold

    def compute_dedup_hash(self, result: ScraperResult) -> str:
        """
        Compute a deduplication hash for a property.

        The hash is based on normalized address and key characteristics.
        """
        # Normalize address
        address_normalized = self.normalizer.normalize(result.address) or ""
        city_normalized = self.normalizer.normalize(result.city) or ""

        # Build hash components
        components = [
            address_normalized,
            city_normalized,
            str(result.bedrooms or ""),
            str(result.bathrooms or ""),
            str(int(result.area_built or 0)),
        ]

        # Create hash
        hash_input = "|".join(components).encode("utf-8")
        return hashlib.sha256(hash_input).hexdigest()[:16]

    async def check_duplicate(
        self,
        result: ScraperResult,
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if a scraped property is a duplicate of an existing one.

        Args:
            result: Scraped property data

        Returns:
            Tuple of (is_duplicate, duplicate_property_id)
        """
        # First, check by exact URL (same listing)
        url_match = await self._check_exact_url(result.source_url)
        if url_match:
            return True, url_match.id

        # Compute dedup hash
        dedup_hash = self.compute_dedup_hash(result)

        # Check for hash match (exact duplicate)
        hash_match = await self._check_hash_match(dedup_hash)
        if hash_match:
            return True, hash_match.id

        # Find candidates by city and similar characteristics
        candidates = await self._find_candidates(result)

        # Score each candidate
        for candidate in candidates:
            score = self._compute_similarity_score(result, candidate)
            if score >= self.features_threshold:
                logger.info(
                    f"Duplicate found: {result.source_url} matches {candidate.source_url} "
                    f"(score: {score:.2f})"
                )
                return True, candidate.id

        return False, None

    async def _check_exact_url(self, url: str) -> Optional[Property]:
        """Check for exact URL match."""
        result = await self.db.execute(
            select(Property).where(Property.source_url == url)
        )
        return result.scalar_one_or_none()

    async def _check_hash_match(self, dedup_hash: str) -> Optional[Property]:
        """Check for matching deduplication hash."""
        result = await self.db.execute(
            select(Property).where(
                and_(
                    Property.dedup_hash == dedup_hash,
                    Property.status != PropertyStatus.DUPLICATE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _find_candidates(
        self,
        result: ScraperResult,
        limit: int = 50,
    ) -> List[Property]:
        """
        Find candidate properties that might be duplicates.

        Uses city and approximate characteristics to narrow down candidates.
        """
        # Normalize city for comparison
        city_normalized = self.normalizer.normalize(result.city)

        # Build query conditions
        conditions = [
            Property.status != PropertyStatus.DUPLICATE,
        ]

        # City filter (case-insensitive)
        if city_normalized:
            conditions.append(
                Property.city.ilike(f"%{result.city}%")
            )

        # Price range filter (±20%)
        if result.price:
            price_min = result.price * Decimal("0.8")
            price_max = result.price * Decimal("1.2")
            conditions.append(
                and_(
                    Property.price >= price_min,
                    Property.price <= price_max,
                )
            )

        # Bedrooms filter (exact match if specified)
        if result.bedrooms is not None:
            conditions.append(
                or_(
                    Property.bedrooms == result.bedrooms,
                    Property.bedrooms.is_(None),
                )
            )

        # Area filter (±15%)
        if result.area_built:
            area_min = result.area_built * Decimal("0.85")
            area_max = result.area_built * Decimal("1.15")
            conditions.append(
                or_(
                    and_(
                        Property.area_built >= area_min,
                        Property.area_built <= area_max,
                    ),
                    Property.area_built.is_(None),
                )
            )

        query = select(Property).where(and_(*conditions)).limit(limit)
        result_db = await self.db.execute(query)
        return list(result_db.scalars().all())

    def _compute_similarity_score(
        self,
        result: ScraperResult,
        candidate: Property,
    ) -> float:
        """
        Compute overall similarity score between scraped data and existing property.

        Returns a score between 0 and 1, where 1 is a perfect match.
        """
        scores = []
        weights = []

        # Address similarity (highest weight)
        address_score = self._compute_address_similarity(result, candidate)
        if address_score is not None:
            scores.append(address_score)
            weights.append(0.4)

        # Price similarity
        price_score = self._compute_price_similarity(result, candidate)
        if price_score is not None:
            scores.append(price_score)
            weights.append(0.2)

        # Characteristics similarity
        char_score = self._compute_characteristics_similarity(result, candidate)
        if char_score is not None:
            scores.append(char_score)
            weights.append(0.25)

        # Geographic proximity
        geo_score = self._compute_geo_similarity(result, candidate)
        if geo_score is not None:
            scores.append(geo_score)
            weights.append(0.15)

        if not scores:
            return 0.0

        # Weighted average
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight

    def _compute_address_similarity(
        self,
        result: ScraperResult,
        candidate: Property,
    ) -> Optional[float]:
        """Compute address similarity using fuzzy matching."""
        result_addr = self.normalizer.normalize(result.address)
        candidate_addr = candidate.address_normalized or self.normalizer.normalize(
            candidate.address
        )

        if not result_addr or not candidate_addr:
            return None

        # Use token set ratio for address comparison
        # This handles word reordering and partial matches well
        similarity = fuzz.token_set_ratio(result_addr, candidate_addr) / 100.0
        return similarity

    def _compute_price_similarity(
        self,
        result: ScraperResult,
        candidate: Property,
    ) -> Optional[float]:
        """Compute price similarity."""
        if not result.price or not candidate.price:
            return None

        # Calculate percentage difference
        price1 = float(result.price)
        price2 = float(candidate.price)

        if max(price1, price2) == 0:
            return None

        diff_pct = abs(price1 - price2) / max(price1, price2)

        # Convert to similarity (1 = identical, 0 = >50% different)
        similarity = max(0, 1 - (diff_pct * 2))
        return similarity

    def _compute_characteristics_similarity(
        self,
        result: ScraperResult,
        candidate: Property,
    ) -> Optional[float]:
        """Compute similarity based on property characteristics."""
        scores = []

        # Bedrooms
        if result.bedrooms is not None and candidate.bedrooms is not None:
            if result.bedrooms == candidate.bedrooms:
                scores.append(1.0)
            else:
                diff = abs(result.bedrooms - candidate.bedrooms)
                scores.append(max(0, 1 - (diff * 0.5)))

        # Bathrooms
        if result.bathrooms is not None and candidate.bathrooms is not None:
            if result.bathrooms == candidate.bathrooms:
                scores.append(1.0)
            else:
                diff = abs(result.bathrooms - candidate.bathrooms)
                scores.append(max(0, 1 - (diff * 0.5)))

        # Area
        if result.area_built and candidate.area_built:
            area1 = float(result.area_built)
            area2 = float(candidate.area_built)
            if max(area1, area2) > 0:
                diff_pct = abs(area1 - area2) / max(area1, area2)
                scores.append(max(0, 1 - (diff_pct * 5)))  # 20% diff = 0 score

        # Floor
        if result.floor is not None and candidate.floor is not None:
            if result.floor == candidate.floor:
                scores.append(1.0)
            else:
                scores.append(0.5)

        return sum(scores) / len(scores) if scores else None

    def _compute_geo_similarity(
        self,
        result: ScraperResult,
        candidate: Property,
    ) -> Optional[float]:
        """Compute geographic proximity similarity."""
        if not all([
            result.latitude, result.longitude,
            candidate.latitude, candidate.longitude,
        ]):
            return None

        # Simple distance calculation (good enough for deduplication)
        lat1 = float(result.latitude)
        lon1 = float(result.longitude)
        lat2 = float(candidate.latitude)
        lon2 = float(candidate.longitude)

        # Approximate distance in km (simplified formula)
        lat_diff = abs(lat1 - lat2) * 111  # ~111 km per degree
        lon_diff = abs(lon1 - lon2) * 85   # ~85 km per degree at 40°N

        distance_km = (lat_diff ** 2 + lon_diff ** 2) ** 0.5

        # Score: 1 if same location, 0 if >500m apart
        if distance_km > 0.5:
            return 0.0
        return 1 - (distance_km * 2)

    async def merge_duplicates(
        self,
        primary_id: int,
        duplicate_ids: List[int],
    ) -> Property:
        """
        Merge duplicate properties into a primary record.

        The primary property is kept, duplicates are marked and linked.
        """
        # Get primary property
        result = await self.db.execute(
            select(Property).where(Property.id == primary_id)
        )
        primary = result.scalar_one()

        # Update duplicates
        for dup_id in duplicate_ids:
            result = await self.db.execute(
                select(Property).where(Property.id == dup_id)
            )
            duplicate = result.scalar_one_or_none()
            if duplicate:
                duplicate.status = PropertyStatus.DUPLICATE
                duplicate.duplicate_of_id = primary_id

        await self.db.commit()
        return primary
