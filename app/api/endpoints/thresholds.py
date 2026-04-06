"""Alert threshold endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import AlertThreshold
from app.infrastructure.database.session import get_db
from app.schemas.network import ThresholdCreate, ThresholdOut

router = APIRouter(prefix="/thresholds", tags=["thresholds"], dependencies=[Depends(get_current_user)])


@router.get("/device/{device_id}", response_model=list[ThresholdOut])
async def get_device_thresholds(device_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AlertThreshold).where(AlertThreshold.device_id == device_id)
    )
    return result.scalars().all()


@router.post("", response_model=ThresholdOut, status_code=201)
async def create_or_update_threshold(body: ThresholdCreate, db: AsyncSession = Depends(get_db)):
    # Upsert: if threshold for this device+metric exists, update it
    result = await db.execute(
        select(AlertThreshold).where(
            AlertThreshold.device_id == body.device_id,
            AlertThreshold.metric_name == body.metric_name,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.warning_value = body.warning_value
        existing.critical_value = body.critical_value
        existing.enabled = body.enabled
        await db.flush()
        await db.refresh(existing)
        return existing

    threshold = AlertThreshold(**body.model_dump())
    db.add(threshold)
    await db.flush()
    await db.refresh(threshold)
    return threshold


@router.delete("/{threshold_id}", status_code=204)
async def delete_threshold(threshold_id: UUID, db: AsyncSession = Depends(get_db)):
    threshold = await db.get(AlertThreshold, threshold_id)
    if not threshold:
        raise HTTPException(status_code=404, detail="Umbral no encontrado")
    await db.delete(threshold)
