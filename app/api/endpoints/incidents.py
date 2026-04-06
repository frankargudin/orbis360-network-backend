"""Incident history endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import Incident, IncidentStatus
from app.infrastructure.database.session import get_db
from app.schemas.network import IncidentCreate, IncidentOut, IncidentUpdate

router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    device_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Incident)
    if status:
        query = query.where(Incident.status == IncidentStatus(status))
    if severity:
        query = query.where(Incident.severity == severity)
    if device_id:
        query = query.where(Incident.device_id == device_id)
    query = query.order_by(Incident.detected_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(incident_id: UUID, db: AsyncSession = Depends(get_db)):
    incident = await db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(incident_id: UUID, body: IncidentUpdate, db: AsyncSession = Depends(get_db)):
    incident = await db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if body.status:
        incident.status = IncidentStatus(body.status)
        if body.status == "acknowledged":
            incident.acknowledged_at = datetime.now(timezone.utc)
        elif body.status == "resolved":
            incident.resolved_at = datetime.now(timezone.utc)

    if body.resolution_notes:
        incident.resolution_notes = body.resolution_notes

    await db.flush()
    await db.refresh(incident)
    return incident
