"""Maintenance window endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import MaintenanceWindow
from app.infrastructure.database.session import get_db
from app.schemas.network import MaintenanceCreate, MaintenanceOut

router = APIRouter(prefix="/maintenance", tags=["maintenance"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[MaintenanceOut])
async def list_maintenance(
    device_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(MaintenanceWindow).order_by(MaintenanceWindow.start_time.desc())
    if device_id:
        query = query.where(MaintenanceWindow.device_id == device_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=MaintenanceOut, status_code=201)
async def create_maintenance(
    body: MaintenanceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=400, detail="La fecha de fin debe ser posterior a la de inicio")

    mw = MaintenanceWindow(
        device_id=body.device_id,
        title=body.title,
        description=body.description,
        start_time=body.start_time,
        end_time=body.end_time,
        created_by=user.get("sub"),
    )
    db.add(mw)
    await db.flush()
    await db.refresh(mw)
    return mw


@router.delete("/{mw_id}", status_code=204)
async def delete_maintenance(mw_id: UUID, db: AsyncSession = Depends(get_db)):
    mw = await db.get(MaintenanceWindow, mw_id)
    if not mw:
        raise HTTPException(status_code=404, detail="Ventana de mantenimiento no encontrada")
    await db.delete(mw)
