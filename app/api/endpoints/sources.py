"""Scraping sources management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.property import ScrapingSource

router = APIRouter()


class SourceCreate(BaseModel):
    """Schema for creating a scraping source."""

    name: str
    base_url: str
    scraper_class: str
    config: dict = {}
    is_active: bool = True


class SourceUpdate(BaseModel):
    """Schema for updating a scraping source."""

    name: Optional[str] = None
    base_url: Optional[str] = None
    scraper_class: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None


class SourceResponse(BaseModel):
    """Schema for scraping source response."""

    id: int
    name: str
    base_url: str
    scraper_class: str
    config: dict
    is_active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=List[SourceResponse])
async def list_sources(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all scraping sources."""
    query = select(ScrapingSource)

    if is_active is not None:
        query = query.where(ScrapingSource.is_active == is_active)

    result = await db.execute(query)
    sources = result.scalars().all()

    return sources


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a scraping source by ID."""
    result = await db.execute(
        select(ScrapingSource).where(ScrapingSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    return source


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(
    data: SourceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new scraping source."""
    # Check if name already exists
    result = await db.execute(
        select(ScrapingSource).where(ScrapingSource.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Source with this name already exists",
        )

    source = ScrapingSource(**data.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return source


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int,
    data: SourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a scraping source."""
    result = await db.execute(
        select(ScrapingSource).where(ScrapingSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(source, field, value)

    await db.commit()
    await db.refresh(source)

    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a scraping source."""
    result = await db.execute(
        select(ScrapingSource).where(ScrapingSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.delete(source)
    await db.commit()
