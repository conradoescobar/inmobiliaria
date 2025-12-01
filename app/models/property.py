"""Property model with PostGIS support for geospatial queries."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Numeric,
    DateTime,
    Boolean,
    ForeignKey,
    Enum,
    Index,
    JSON,
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.db.session import Base


class PropertyType(str, enum.Enum):
    """Types of properties."""

    APARTMENT = "apartment"
    HOUSE = "house"
    STUDIO = "studio"
    PENTHOUSE = "penthouse"
    DUPLEX = "duplex"
    LOFT = "loft"
    LAND = "land"
    COMMERCIAL = "commercial"
    OFFICE = "office"
    WAREHOUSE = "warehouse"
    PARKING = "parking"
    OTHER = "other"


class OperationType(str, enum.Enum):
    """Type of operation (sale or rent)."""

    SALE = "sale"
    RENT = "rent"
    RENT_TO_OWN = "rent_to_own"


class PropertyStatus(str, enum.Enum):
    """Status of the property listing."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SOLD = "sold"
    RENTED = "rented"
    DUPLICATE = "duplicate"


class ScrapingSource(Base):
    """Source portal for scraping properties."""

    __tablename__ = "scraping_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    base_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    scraper_class = Column(String(100), nullable=False)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    properties = relationship("Property", back_populates="source")
    scraping_runs = relationship("ScrapingRun", back_populates="source")


class ScrapingRun(Base):
    """Record of scraping execution."""

    __tablename__ = "scraping_runs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("scraping_sources.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="running")
    properties_found = Column(Integer, default=0)
    properties_new = Column(Integer, default=0)
    properties_updated = Column(Integer, default=0)
    properties_duplicates = Column(Integer, default=0)
    errors = Column(JSON, default=list)

    # Relationships
    source = relationship("ScrapingSource", back_populates="scraping_runs")


class Property(Base):
    """Real estate property model with geospatial support."""

    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)

    # External identification
    external_id = Column(String(100), nullable=True)
    source_id = Column(Integer, ForeignKey("scraping_sources.id"), nullable=False)
    source_url = Column(String(1000), nullable=False, unique=True)

    # Basic information
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    property_type = Column(Enum(PropertyType), nullable=False)
    operation_type = Column(Enum(OperationType), nullable=False)
    status = Column(Enum(PropertyStatus), default=PropertyStatus.ACTIVE)

    # Pricing
    price = Column(Numeric(12, 2), nullable=False)
    price_currency = Column(String(3), default="EUR")
    price_per_sqm = Column(Numeric(10, 2), nullable=True)
    community_fees = Column(Numeric(10, 2), nullable=True)

    # Location
    address = Column(String(500), nullable=True)
    address_normalized = Column(String(500), nullable=True)
    neighborhood = Column(String(200), nullable=True)
    city = Column(String(200), nullable=False)
    province = Column(String(200), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), default="España")

    # PostGIS geometry for geospatial queries
    location = Column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)

    # Characteristics
    area_built = Column(Numeric(10, 2), nullable=True)
    area_usable = Column(Numeric(10, 2), nullable=True)
    area_plot = Column(Numeric(10, 2), nullable=True)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    floor = Column(Integer, nullable=True)
    total_floors = Column(Integer, nullable=True)
    has_elevator = Column(Boolean, nullable=True)
    has_parking = Column(Boolean, nullable=True)
    parking_spaces = Column(Integer, nullable=True)
    has_terrace = Column(Boolean, nullable=True)
    has_balcony = Column(Boolean, nullable=True)
    has_garden = Column(Boolean, nullable=True)
    has_pool = Column(Boolean, nullable=True)
    has_storage = Column(Boolean, nullable=True)
    has_air_conditioning = Column(Boolean, nullable=True)
    has_heating = Column(Boolean, nullable=True)
    heating_type = Column(String(100), nullable=True)
    orientation = Column(String(50), nullable=True)
    year_built = Column(Integer, nullable=True)
    is_new_construction = Column(Boolean, default=False)
    needs_renovation = Column(Boolean, default=False)

    # Energy certificate
    energy_rating = Column(String(10), nullable=True)
    energy_consumption = Column(Numeric(10, 2), nullable=True)
    emissions_rating = Column(String(10), nullable=True)

    # Additional features stored as JSON
    features = Column(JSON, default=list)
    raw_data = Column(JSON, default=dict)

    # Deduplication
    duplicate_of_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    dedup_hash = Column(String(64), nullable=True, index=True)

    # Timestamps
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    price_changed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source = relationship("ScrapingSource", back_populates="properties")
    images = relationship("PropertyImage", back_populates="property", cascade="all, delete-orphan")
    duplicate_of = relationship("Property", remote_side=[id], backref="duplicates")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_properties_city_operation", "city", "operation_type"),
        Index("ix_properties_price", "price"),
        Index("ix_properties_bedrooms", "bedrooms"),
        Index("ix_properties_area", "area_built"),
        Index("ix_properties_location", "location", postgresql_using="gist"),
    )


class PropertyImage(Base):
    """Property images."""

    __tablename__ = "property_images"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    is_main = Column(Boolean, default=False)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    property = relationship("Property", back_populates="images")
