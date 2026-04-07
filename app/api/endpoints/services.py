"""Service check endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.domain.models.network import ServiceCheck, ServiceCheckStatus
from app.infrastructure.database.session import get_db
from app.infrastructure.monitoring.service_checker import run_service_check

router = APIRouter(prefix="/services", tags=["services"], dependencies=[Depends(get_current_user)])


class ServiceCheckCreate(BaseModel):
    device_id: UUID
    name: str
    check_type: str
    target: str
    port: int | None = None
    expected_status: int | None = None
    timeout_seconds: int = 5


class ServiceCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    device_id: UUID
    name: str
    check_type: str
    target: str
    port: int | None
    expected_status: int | None
    enabled: bool
    status: str
    last_check: str | None
    last_response_ms: float | None
    last_error: str | None
    consecutive_failures: int


@router.get("/device/{device_id}", response_model=list[ServiceCheckOut])
async def get_device_services(device_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ServiceCheck).where(ServiceCheck.device_id == device_id)
    )
    return result.scalars().all()


@router.get("", response_model=list[ServiceCheckOut])
async def list_all_services(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceCheck).order_by(ServiceCheck.name))
    return result.scalars().all()


@router.post("", response_model=ServiceCheckOut, status_code=201, dependencies=[Depends(require_role("operator"))])
async def create_service_check(body: ServiceCheckCreate, db: AsyncSession = Depends(get_db)):
    svc = ServiceCheck(**body.model_dump())
    db.add(svc)
    await db.flush()
    await db.refresh(svc)
    return svc


@router.delete("/{service_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def delete_service_check(service_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = await db.get(ServiceCheck, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    await db.delete(svc)


@router.post("/{service_id}/check")
async def run_check_now(service_id: UUID, db: AsyncSession = Depends(get_db)):
    """Run a service check immediately and return the result."""
    svc = await db.get(ServiceCheck, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    from datetime import datetime, timezone
    result = await run_service_check(
        svc.check_type.value, svc.target, svc.port, svc.expected_status, svc.timeout_seconds
    )

    svc.last_check = datetime.now(timezone.utc)
    svc.last_response_ms = result.response_ms
    svc.last_error = result.error

    if result.ok:
        svc.status = ServiceCheckStatus.OK
        svc.consecutive_failures = 0
    else:
        svc.consecutive_failures += 1
        svc.status = ServiceCheckStatus.CRITICAL if svc.consecutive_failures >= 3 else ServiceCheckStatus.WARNING

    await db.flush()
    await db.refresh(svc)

    return {
        "ok": result.ok,
        "response_ms": result.response_ms,
        "error": result.error,
        "status": svc.status.value,
    }
