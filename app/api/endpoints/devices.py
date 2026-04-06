"""Device management endpoints."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.events import ws_manager
from app.domain.models.network import Device, DeviceStatus, DeviceType, Incident, IncidentSeverity, IncidentStatus
from app.infrastructure.database.session import get_db
from app.infrastructure.ssh.client import SSHClient
from app.schemas.network import DeviceCreate, DeviceOut, DeviceUpdate, RebootRequest, RebootResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    status: str | None = None,
    device_type: str | None = None,
    location_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(Device)
    if status:
        query = query.where(Device.status == DeviceStatus(status))
    if device_type:
        query = query.where(Device.device_type == DeviceType(device_type))
    if location_id:
        query = query.where(Device.location_id == location_id)
    query = query.offset(skip).limit(limit).order_by(Device.hostname)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary")
async def devices_summary(db: AsyncSession = Depends(get_db)):
    """Quick stats: total, up, down, degraded counts."""
    result = await db.execute(
        select(Device.status, func.count(Device.id)).group_by(Device.status)
    )
    counts = {row[0].value: row[1] for row in result.all()}
    return {
        "total": sum(counts.values()),
        "up": counts.get("up", 0),
        "down": counts.get("down", 0),
        "degraded": counts.get("degraded", 0),
        "unknown": counts.get("unknown", 0),
        "maintenance": counts.get("maintenance", 0),
    }


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: UUID, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(body: DeviceCreate, db: AsyncSession = Depends(get_db)):
    device = Device(**body.model_dump())
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(device_id: UUID, body: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)

    await db.flush()
    await db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: UUID, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(device)


@router.post("/{device_id}/reboot", response_model=RebootResponse)
async def reboot_device(
    device_id: UUID,
    body: RebootRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reboot a device via SSH. Requires SSH credentials configured on the device."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Debes confirmar el reinicio enviando confirm=true")

    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    if not device.ssh_username or not device.ssh_password:
        raise HTTPException(
            status_code=400,
            detail="Este dispositivo no tiene credenciales SSH configuradas. Edita el dispositivo para agregar usuario y contraseña SSH.",
        )

    # Execute reboot via SSH
    result = await SSHClient.reboot_device(
        host=device.ip_address,
        username=device.ssh_username,
        password=device.ssh_password,
        device_type=device.device_type.value,
        vendor=device.vendor,
        port=device.ssh_port,
    )

    # Log as incident
    incident = Incident(
        title=f"Reinicio {'exitoso' if result.success else 'fallido'}: {device.hostname}",
        description=f"Reinicio iniciado por usuario {user.get('sub', 'unknown')}. Comando: {result.command}. Resultado: {result.output or result.error}",
        severity=IncidentSeverity.WARNING if result.success else IncidentSeverity.MINOR,
        status=IncidentStatus.RESOLVED if result.success else IncidentStatus.OPEN,
        device_id=device.id,
        detected_at=datetime.now(timezone.utc),
        resolved_at=datetime.now(timezone.utc) if result.success else None,
    )
    db.add(incident)

    # Broadcast reboot event
    await ws_manager.broadcast("device_reboot", {
        "device_id": str(device.id),
        "hostname": device.hostname,
        "success": result.success,
        "message": result.output or result.error,
    })

    logger.info(f"Reboot {'OK' if result.success else 'FAILED'} for {device.hostname}: {result.output or result.error}")

    return RebootResponse(
        success=result.success,
        device_id=device.id,
        hostname=device.hostname,
        command_sent=result.command,
        output=result.output,
        error=result.error,
    )
