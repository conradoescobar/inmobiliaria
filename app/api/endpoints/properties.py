"""Property CRUD endpoints."""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.property import PropertyType, OperationType, PropertyStatus
from app.schemas.property import (
    PropertyCreate,
    PropertyUpdate,
    PropertyResponse,
    PropertyListResponse,
    PropertySearchParams,
    GeoSearchParams,
)
from app.services.property_service import PropertyService

router = APIRouter()


@router.get("", response_model=PropertyListResponse)
async def list_properties(
    # Basic filters
    operation_type: Optional[OperationType] = None,
    property_type: Optional[PropertyType] = None,
    status: Optional[PropertyStatus] = PropertyStatus.ACTIVE,
    # Location filters
    city: Optional[str] = None,
    province: Optional[str] = None,
    neighborhood: Optional[str] = None,
    postal_code: Optional[str] = None,
    # Price filters
    price_min: Optional[Decimal] = Query(None, ge=0),
    price_max: Optional[Decimal] = Query(None, ge=0),
    # Area filters
    area_min: Optional[Decimal] = Query(None, ge=0),
    area_max: Optional[Decimal] = Query(None, ge=0),
    # Room filters
    bedrooms_min: Optional[int] = Query(None, ge=0),
    bedrooms_max: Optional[int] = Query(None, ge=0),
    bathrooms_min: Optional[int] = Query(None, ge=0),
    # Feature filters
    has_parking: Optional[bool] = None,
    has_elevator: Optional[bool] = None,
    has_terrace: Optional[bool] = None,
    has_pool: Optional[bool] = None,
    has_garden: Optional[bool] = None,
    has_air_conditioning: Optional[bool] = None,
    # Pagination
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    # Sorting
    sort_by: str = "created_at",
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    # Database session
    db: AsyncSession = Depends(get_db),
):
    """
    List properties with filtering and pagination.

    Supports various filters including price range, location,
    property characteristics, and amenities.
    """
    params = PropertySearchParams(
        operation_type=operation_type,
        property_type=property_type,
        status=status,
        city=city,
        province=province,
        neighborhood=neighborhood,
        postal_code=postal_code,
        price_min=price_min,
        price_max=price_max,
        area_min=area_min,
        area_max=area_max,
        bedrooms_min=bedrooms_min,
        bedrooms_max=bedrooms_max,
        bathrooms_min=bathrooms_min,
        has_parking=has_parking,
        has_elevator=has_elevator,
        has_terrace=has_terrace,
        has_pool=has_pool,
        has_garden=has_garden,
        has_air_conditioning=has_air_conditioning,
        page=page,
        size=size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    service = PropertyService(db)
    properties, total = await service.search(params)

    pages = (total + size - 1) // size  # Ceiling division

    return PropertyListResponse(
        items=properties,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/nearby", response_model=PropertyListResponse)
async def search_nearby(
    latitude: Decimal = Query(..., ge=-90, le=90),
    longitude: Decimal = Query(..., ge=-180, le=180),
    radius_km: Decimal = Query(5, ge=0.1, le=100),
    operation_type: Optional[OperationType] = None,
    property_type: Optional[PropertyType] = None,
    price_min: Optional[Decimal] = Query(None, ge=0),
    price_max: Optional[Decimal] = Query(None, ge=0),
    bedrooms_min: Optional[int] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Search properties near a geographic point.

    Uses PostGIS spatial queries for efficient radius search.
    Results are ordered by distance from the specified point.
    """
    params = GeoSearchParams(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        operation_type=operation_type,
        property_type=property_type,
        price_min=price_min,
        price_max=price_max,
        bedrooms_min=bedrooms_min,
        page=page,
        size=size,
    )

    service = PropertyService(db)
    properties, total = await service.search_by_location(params)

    pages = (total + size - 1) // size

    return PropertyListResponse(
        items=properties,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a property by ID."""
    service = PropertyService(db)
    property_obj = await service.get(property_id)

    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")

    return property_obj


@router.post("", response_model=PropertyResponse, status_code=201)
async def create_property(
    data: PropertyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new property."""
    service = PropertyService(db)

    # Check if URL already exists
    existing = await service.get_by_url(data.source_url)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Property with this URL already exists",
        )

    property_obj = await service.create(data)
    return property_obj


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: int,
    data: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a property."""
    service = PropertyService(db)
    property_obj = await service.update(property_id, data)

    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")

    return property_obj


@router.delete("/{property_id}", status_code=204)
async def delete_property(
    property_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a property."""
    service = PropertyService(db)
    deleted = await service.delete(property_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Property not found")
