"""Property service for CRUD operations."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Tuple

from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID, ST_Distance
from sqlalchemy import select, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.property import Property, PropertyImage, PropertyStatus
from app.schemas.property import (
    PropertyCreate,
    PropertyUpdate,
    PropertySearchParams,
    GeoSearchParams,
)
from app.services.scrapers.base import ScraperResult
from app.services.deduplication.normalizer import AddressNormalizer

logger = logging.getLogger(__name__)


class PropertyService:
    """Service for property CRUD operations."""

    def __init__(self, db: AsyncSession):
        """Initialize property service."""
        self.db = db
        self.normalizer = AddressNormalizer()

    async def create(self, data: PropertyCreate) -> Property:
        """Create a new property."""
        # Normalize address
        address_normalized = self.normalizer.normalize(data.address)

        # Calculate price per sqm
        price_per_sqm = None
        if data.price and data.area_built:
            price_per_sqm = data.price / data.area_built

        # Create property
        property_data = data.model_dump(exclude={"images", "raw_data"})
        property_data["address_normalized"] = address_normalized
        property_data["price_per_sqm"] = price_per_sqm

        # Create location point if coordinates provided
        if data.latitude and data.longitude:
            property_data["location"] = func.ST_SetSRID(
                func.ST_MakePoint(float(data.longitude), float(data.latitude)),
                4326,
            )

        db_property = Property(**property_data)
        db_property.raw_data = data.raw_data

        self.db.add(db_property)
        await self.db.flush()

        # Add images
        for idx, img_data in enumerate(data.images):
            image = PropertyImage(
                property_id=db_property.id,
                url=img_data.url,
                is_main=img_data.is_main or idx == 0,
                order=img_data.order or idx,
            )
            self.db.add(image)

        await self.db.commit()
        await self.db.refresh(db_property)

        return db_property

    async def create_from_scraper(
        self,
        result: ScraperResult,
        source_id: int,
    ) -> Property:
        """Create a property from scraper result."""
        from app.services.deduplication.service import DeduplicationService

        dedup_service = DeduplicationService(self.db)

        # Normalize address
        address_normalized = self.normalizer.normalize(result.address)

        # Calculate price per sqm
        price_per_sqm = None
        if result.price and result.area_built:
            price_per_sqm = result.price / result.area_built

        # Compute dedup hash
        dedup_hash = dedup_service.compute_dedup_hash(result)

        # Create property
        db_property = Property(
            external_id=result.external_id,
            source_id=source_id,
            source_url=result.source_url,
            title=result.title,
            description=result.description,
            property_type=result.property_type,
            operation_type=result.operation_type,
            price=result.price,
            price_currency=result.price_currency,
            price_per_sqm=price_per_sqm,
            community_fees=result.community_fees,
            address=result.address,
            address_normalized=address_normalized,
            neighborhood=result.neighborhood,
            city=result.city,
            province=result.province,
            postal_code=result.postal_code,
            latitude=result.latitude,
            longitude=result.longitude,
            area_built=result.area_built,
            area_usable=result.area_usable,
            area_plot=result.area_plot,
            bedrooms=result.bedrooms,
            bathrooms=result.bathrooms,
            floor=result.floor,
            total_floors=result.total_floors,
            has_elevator=result.has_elevator,
            has_parking=result.has_parking,
            parking_spaces=result.parking_spaces,
            has_terrace=result.has_terrace,
            has_balcony=result.has_balcony,
            has_garden=result.has_garden,
            has_pool=result.has_pool,
            has_storage=result.has_storage,
            has_air_conditioning=result.has_air_conditioning,
            has_heating=result.has_heating,
            heating_type=result.heating_type,
            orientation=result.orientation,
            year_built=result.year_built,
            is_new_construction=result.is_new_construction,
            needs_renovation=result.needs_renovation,
            energy_rating=result.energy_rating,
            energy_consumption=result.energy_consumption,
            emissions_rating=result.emissions_rating,
            features=result.features,
            raw_data=result.raw_data,
            dedup_hash=dedup_hash,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )

        # Set location point
        if result.latitude and result.longitude:
            db_property.location = func.ST_SetSRID(
                func.ST_MakePoint(float(result.longitude), float(result.latitude)),
                4326,
            )

        self.db.add(db_property)
        await self.db.flush()

        # Add images
        for idx, img_url in enumerate(result.images):
            image = PropertyImage(
                property_id=db_property.id,
                url=img_url,
                is_main=idx == 0,
                order=idx,
            )
            self.db.add(image)

        await self.db.commit()
        await self.db.refresh(db_property)

        return db_property

    async def update_from_scraper(
        self,
        property_id: int,
        result: ScraperResult,
    ) -> Property:
        """Update an existing property from scraper result."""
        db_property = await self.get(property_id)
        if not db_property:
            raise ValueError(f"Property {property_id} not found")

        # Check for price change
        if result.price and result.price != db_property.price:
            db_property.price_changed_at = datetime.utcnow()

        # Update fields
        db_property.title = result.title
        db_property.description = result.description
        db_property.price = result.price

        if result.area_built:
            db_property.area_built = result.area_built
            if result.price:
                db_property.price_per_sqm = result.price / result.area_built

        db_property.bedrooms = result.bedrooms or db_property.bedrooms
        db_property.bathrooms = result.bathrooms or db_property.bathrooms
        db_property.features = result.features or db_property.features
        db_property.last_seen_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(db_property)

        return db_property

    async def get(self, property_id: int) -> Optional[Property]:
        """Get a property by ID."""
        result = await self.db.execute(
            select(Property)
            .options(selectinload(Property.images))
            .where(Property.id == property_id)
        )
        return result.scalar_one_or_none()

    async def get_by_url(self, url: str) -> Optional[Property]:
        """Get a property by source URL."""
        result = await self.db.execute(
            select(Property).where(Property.source_url == url)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        property_id: int,
        data: PropertyUpdate,
    ) -> Optional[Property]:
        """Update a property."""
        db_property = await self.get(property_id)
        if not db_property:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Check for price change
        if "price" in update_data and update_data["price"] != db_property.price:
            db_property.price_changed_at = datetime.utcnow()

        # Update fields
        for field, value in update_data.items():
            setattr(db_property, field, value)

        # Update normalized address if address changed
        if "address" in update_data:
            db_property.address_normalized = self.normalizer.normalize(
                update_data["address"]
            )

        # Update location if coordinates changed
        if "latitude" in update_data or "longitude" in update_data:
            lat = update_data.get("latitude") or db_property.latitude
            lon = update_data.get("longitude") or db_property.longitude
            if lat and lon:
                db_property.location = func.ST_SetSRID(
                    func.ST_MakePoint(float(lon), float(lat)),
                    4326,
                )

        # Recalculate price per sqm
        if db_property.price and db_property.area_built:
            db_property.price_per_sqm = db_property.price / db_property.area_built

        await self.db.commit()
        await self.db.refresh(db_property)

        return db_property

    async def delete(self, property_id: int) -> bool:
        """Delete a property."""
        db_property = await self.get(property_id)
        if not db_property:
            return False

        await self.db.delete(db_property)
        await self.db.commit()
        return True

    async def search(
        self,
        params: PropertySearchParams,
    ) -> Tuple[List[Property], int]:
        """
        Search properties with filters.

        Returns:
            Tuple of (properties list, total count)
        """
        # Build query
        query = select(Property).options(selectinload(Property.images))
        count_query = select(func.count(Property.id))

        # Apply filters
        conditions = []

        if params.status:
            conditions.append(Property.status == params.status)

        if params.operation_type:
            conditions.append(Property.operation_type == params.operation_type)

        if params.property_type:
            conditions.append(Property.property_type == params.property_type)

        if params.city:
            conditions.append(Property.city.ilike(f"%{params.city}%"))

        if params.province:
            conditions.append(Property.province.ilike(f"%{params.province}%"))

        if params.neighborhood:
            conditions.append(Property.neighborhood.ilike(f"%{params.neighborhood}%"))

        if params.postal_code:
            conditions.append(Property.postal_code == params.postal_code)

        if params.price_min:
            conditions.append(Property.price >= params.price_min)

        if params.price_max:
            conditions.append(Property.price <= params.price_max)

        if params.area_min:
            conditions.append(Property.area_built >= params.area_min)

        if params.area_max:
            conditions.append(Property.area_built <= params.area_max)

        if params.bedrooms_min:
            conditions.append(Property.bedrooms >= params.bedrooms_min)

        if params.bedrooms_max:
            conditions.append(Property.bedrooms <= params.bedrooms_max)

        if params.bathrooms_min:
            conditions.append(Property.bathrooms >= params.bathrooms_min)

        # Boolean filters
        if params.has_parking is not None:
            conditions.append(Property.has_parking == params.has_parking)

        if params.has_elevator is not None:
            conditions.append(Property.has_elevator == params.has_elevator)

        if params.has_terrace is not None:
            conditions.append(Property.has_terrace == params.has_terrace)

        if params.has_pool is not None:
            conditions.append(Property.has_pool == params.has_pool)

        if params.has_garden is not None:
            conditions.append(Property.has_garden == params.has_garden)

        if params.has_air_conditioning is not None:
            conditions.append(Property.has_air_conditioning == params.has_air_conditioning)

        # Apply conditions
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        # Apply sorting
        sort_column = getattr(Property, params.sort_by, Property.created_at)
        if params.sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        # Apply pagination
        offset = (params.page - 1) * params.size
        query = query.offset(offset).limit(params.size)

        # Execute query
        result = await self.db.execute(query)
        properties = list(result.scalars().all())

        return properties, total

    async def search_by_location(
        self,
        params: GeoSearchParams,
    ) -> Tuple[List[Property], int]:
        """
        Search properties within a radius of a geographic point.

        Uses PostGIS ST_DWithin for efficient spatial queries.
        """
        # Convert radius to meters for ST_DWithin
        radius_meters = float(params.radius_km) * 1000

        # Create point from coordinates
        search_point = func.ST_SetSRID(
            func.ST_MakePoint(float(params.longitude), float(params.latitude)),
            4326,
        )

        # Build query with spatial filter
        query = (
            select(Property)
            .options(selectinload(Property.images))
            .where(
                ST_DWithin(
                    Property.location,
                    func.ST_Geography(search_point),
                    radius_meters,
                )
            )
        )

        count_query = select(func.count(Property.id)).where(
            ST_DWithin(
                Property.location,
                func.ST_Geography(search_point),
                radius_meters,
            )
        )

        # Apply additional filters
        conditions = [Property.status == PropertyStatus.ACTIVE]

        if params.operation_type:
            conditions.append(Property.operation_type == params.operation_type)

        if params.property_type:
            conditions.append(Property.property_type == params.property_type)

        if params.price_min:
            conditions.append(Property.price >= params.price_min)

        if params.price_max:
            conditions.append(Property.price <= params.price_max)

        if params.bedrooms_min:
            conditions.append(Property.bedrooms >= params.bedrooms_min)

        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

        # Order by distance
        query = query.order_by(
            ST_Distance(Property.location, search_point)
        )

        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        # Apply pagination
        offset = (params.page - 1) * params.size
        query = query.offset(offset).limit(params.size)

        # Execute query
        result = await self.db.execute(query)
        properties = list(result.scalars().all())

        return properties, total
