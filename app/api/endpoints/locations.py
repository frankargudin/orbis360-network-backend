"""Location management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import Location
from app.infrastructure.database.session import get_db
from app.schemas.network import LocationCreate, LocationOut

router = APIRouter(prefix="/locations", tags=["locations"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[LocationOut])
async def list_locations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Location).order_by(Location.building, Location.floor))
    return result.scalars().all()


@router.post("", response_model=LocationOut, status_code=201)
async def create_location(body: LocationCreate, db: AsyncSession = Depends(get_db)):
    location = Location(**body.model_dump())
    db.add(location)
    await db.flush()
    await db.refresh(location)
    return location


@router.delete("/{location_id}", status_code=204)
async def delete_location(location_id: UUID, db: AsyncSession = Depends(get_db)):
    location = await db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    await db.delete(location)
