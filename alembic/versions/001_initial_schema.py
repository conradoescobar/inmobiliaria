"""Initial schema with PostGIS support.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Create scraping_sources table
    op.create_table(
        "scraping_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("scraper_class", sa.String(100), nullable=False),
        sa.Column("config", sa.JSON(), default=dict),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_scraping_sources_id", "scraping_sources", ["id"])

    # Create scraping_runs table
    op.create_table(
        "scraping_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(50), default="running"),
        sa.Column("properties_found", sa.Integer(), default=0),
        sa.Column("properties_new", sa.Integer(), default=0),
        sa.Column("properties_updated", sa.Integer(), default=0),
        sa.Column("properties_duplicates", sa.Integer(), default=0),
        sa.Column("errors", sa.JSON(), default=list),
        sa.ForeignKeyConstraint(["source_id"], ["scraping_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scraping_runs_id", "scraping_runs", ["id"])

    # Create properties table with PostGIS geometry
    op.create_table(
        "properties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "property_type",
            sa.Enum(
                "apartment", "house", "studio", "penthouse", "duplex", "loft",
                "land", "commercial", "office", "warehouse", "parking", "other",
                name="propertytype",
            ),
            nullable=False,
        ),
        sa.Column(
            "operation_type",
            sa.Enum("sale", "rent", "rent_to_own", name="operationtype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "sold", "rented", "duplicate", name="propertystatus"),
            default="active",
        ),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_currency", sa.String(3), default="EUR"),
        sa.Column("price_per_sqm", sa.Numeric(10, 2), nullable=True),
        sa.Column("community_fees", sa.Numeric(10, 2), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("address_normalized", sa.String(500), nullable=True),
        sa.Column("neighborhood", sa.String(200), nullable=True),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("province", sa.String(200), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), default="España"),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("area_built", sa.Numeric(10, 2), nullable=True),
        sa.Column("area_usable", sa.Numeric(10, 2), nullable=True),
        sa.Column("area_plot", sa.Numeric(10, 2), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("total_floors", sa.Integer(), nullable=True),
        sa.Column("has_elevator", sa.Boolean(), nullable=True),
        sa.Column("has_parking", sa.Boolean(), nullable=True),
        sa.Column("parking_spaces", sa.Integer(), nullable=True),
        sa.Column("has_terrace", sa.Boolean(), nullable=True),
        sa.Column("has_balcony", sa.Boolean(), nullable=True),
        sa.Column("has_garden", sa.Boolean(), nullable=True),
        sa.Column("has_pool", sa.Boolean(), nullable=True),
        sa.Column("has_storage", sa.Boolean(), nullable=True),
        sa.Column("has_air_conditioning", sa.Boolean(), nullable=True),
        sa.Column("has_heating", sa.Boolean(), nullable=True),
        sa.Column("heating_type", sa.String(100), nullable=True),
        sa.Column("orientation", sa.String(50), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("is_new_construction", sa.Boolean(), default=False),
        sa.Column("needs_renovation", sa.Boolean(), default=False),
        sa.Column("energy_rating", sa.String(10), nullable=True),
        sa.Column("energy_consumption", sa.Numeric(10, 2), nullable=True),
        sa.Column("emissions_rating", sa.String(10), nullable=True),
        sa.Column("features", sa.JSON(), default=list),
        sa.Column("raw_data", sa.JSON(), default=dict),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("price_changed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["scraping_sources.id"]),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url"),
    )

    # Create indexes
    op.create_index("ix_properties_id", "properties", ["id"])
    op.create_index("ix_properties_dedup_hash", "properties", ["dedup_hash"])
    op.create_index("ix_properties_city_operation", "properties", ["city", "operation_type"])
    op.create_index("ix_properties_price", "properties", ["price"])
    op.create_index("ix_properties_bedrooms", "properties", ["bedrooms"])
    op.create_index("ix_properties_area", "properties", ["area_built"])

    # Create spatial index for PostGIS
    op.execute(
        "CREATE INDEX ix_properties_location ON properties USING GIST (location)"
    )

    # Create property_images table
    op.create_table(
        "property_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("is_main", sa.Boolean(), default=False),
        sa.Column("order", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_property_images_id", "property_images", ["id"])


def downgrade() -> None:
    op.drop_table("property_images")
    op.drop_index("ix_properties_location", "properties")
    op.drop_table("properties")
    op.drop_table("scraping_runs")
    op.drop_table("scraping_sources")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS propertystatus")
    op.execute("DROP TYPE IF EXISTS operationtype")
    op.execute("DROP TYPE IF EXISTS propertytype")
