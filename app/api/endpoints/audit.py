"""Audit log endpoints."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime

from app.core.security import get_current_user
from app.domain.models.network import AuditLog
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(get_current_user)])


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    entity_name: str | None
    details: str | None
    created_at: datetime


@router.get("", response_model=list[AuditOut])
async def list_audit_log(
    entity_type: str | None = None,
    entity_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()
