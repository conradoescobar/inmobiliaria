"""Pydantic schemas for property data validation."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.property import PropertyType, OperationType, PropertyStatus


class PropertyImageSchema(BaseModel):
    """Schema for property images."""

    url: str
    is_main: bool = False
    order: int = 0


class PropertyBase(BaseModel):
    """Base schema for property data."""

    title: str = Field(..., min_length=5, max_length=500)
    description: Optional[str] = None
    property_type: PropertyType
    operation_type: OperationType

    # Pricing
    price: Decimal = Field(..., gt=0)
    price_currency: str = Field(default="EUR", max_length=3)
    community_fees: Optional[Decimal] = None

    # Location
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    city: str = Field(..., min_length=2, max_length=200)
    province: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "España"
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)

    # Characteristics
    area_built: Optional[Decimal] = Field(None, gt=0)
    area_usable: Optional[Decimal] = Field(None, gt=0)
    area_plot: Optional[Decimal] = Field(None, gt=0)
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    floor: Optional[int] = None
    total_floors: Optional[int] = Field(None, ge=0)
    has_elevator: Optional[bool] = None
    has_parking: Optional[bool] = None
    parking_spaces: Optional[int] = Field(None, ge=0)
    has_terrace: Optional[bool] = None
    has_balcony: Optional[bool] = None
    has_garden: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_storage: Optional[bool] = None
    has_air_conditioning: Optional[bool] = None
    has_heating: Optional[bool] = None
    heating_type: Optional[str] = None
    orientation: Optional[str] = None
    year_built: Optional[int] = Field(None, ge=1800, le=2100)
    is_new_construction: bool = False
    needs_renovation: bool = False

    # Energy
    energy_rating: Optional[str] = Field(None, pattern="^[A-G]$")
    energy_consumption: Optional[Decimal] = None
    emissions_rating: Optional[str] = Field(None, pattern="^[A-G]$")

    # Additional features
    features: List[str] = Field(default_factory=list)


class PropertyCreate(PropertyBase):
    """Schema for creating a new property."""

    source_url: str
    external_id: Optional[str] = None
    source_id: int
    images: List[PropertyImageSchema] = Field(default_factory=list)
    raw_data: dict = Field(default_factory=dict)


class PropertyUpdate(BaseModel):
    """Schema for updating a property."""

    title: Optional[str] = Field(None, min_length=5, max_length=500)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0)
    status: Optional[PropertyStatus] = None

    # Location updates
    address: Optional[str] = None
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)

    # Characteristics updates
    area_built: Optional[Decimal] = Field(None, gt=0)
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)

    # Features
    features: Optional[List[str]] = None


class PropertyImageResponse(BaseModel):
    """Schema for property image response."""

    id: int
    url: str
    is_main: bool
    order: int

    class Config:
        from_attributes = True


class PropertyResponse(PropertyBase):
    """Schema for property response."""

    id: int
    external_id: Optional[str]
    source_id: int
    source_url: str
    status: PropertyStatus
    price_per_sqm: Optional[Decimal]
    address_normalized: Optional[str]
    dedup_hash: Optional[str]
    duplicate_of_id: Optional[int]
    first_seen_at: datetime
    last_seen_at: datetime
    price_changed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    images: List[PropertyImageResponse] = []

    class Config:
        from_attributes = True


class PropertyListResponse(BaseModel):
    """Schema for paginated property list response."""

    items: List[PropertyResponse]
    total: int
    page: int
    size: int
    pages: int


class PropertySearchParams(BaseModel):
    """Schema for property search parameters."""

    # Basic filters
    operation_type: Optional[OperationType] = None
    property_type: Optional[PropertyType] = None
    status: Optional[PropertyStatus] = PropertyStatus.ACTIVE

    # Location filters
    city: Optional[str] = None
    province: Optional[str] = None
    neighborhood: Optional[str] = None
    postal_code: Optional[str] = None

    # Price filters
    price_min: Optional[Decimal] = Field(None, ge=0)
    price_max: Optional[Decimal] = Field(None, ge=0)

    # Area filters
    area_min: Optional[Decimal] = Field(None, ge=0)
    area_max: Optional[Decimal] = Field(None, ge=0)

    # Room filters
    bedrooms_min: Optional[int] = Field(None, ge=0)
    bedrooms_max: Optional[int] = Field(None, ge=0)
    bathrooms_min: Optional[int] = Field(None, ge=0)

    # Features filters
    has_parking: Optional[bool] = None
    has_elevator: Optional[bool] = None
    has_terrace: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_garden: Optional[bool] = None
    has_air_conditioning: Optional[bool] = None

    # Pagination
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)

    # Sorting
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")

    @field_validator("price_max")
    @classmethod
    def validate_price_range(cls, v, info):
        if v is not None and info.data.get("price_min") is not None:
            if v < info.data["price_min"]:
                raise ValueError("price_max must be greater than price_min")
        return v


class GeoSearchParams(BaseModel):
    """Schema for geospatial search parameters."""

    latitude: Decimal = Field(..., ge=-90, le=90)
    longitude: Decimal = Field(..., ge=-180, le=180)
    radius_km: Decimal = Field(default=5, ge=0.1, le=100)

    # Include standard search params
    operation_type: Optional[OperationType] = None
    property_type: Optional[PropertyType] = None
    price_min: Optional[Decimal] = Field(None, ge=0)
    price_max: Optional[Decimal] = Field(None, ge=0)
    bedrooms_min: Optional[int] = Field(None, ge=0)

    # Pagination
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
