"""Metrics and analytics endpoints."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import Metric
from app.infrastructure.database.session import get_db
from app.schemas.network import MetricOut

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)])


@router.get("/device/{device_id}", response_model=list[MetricOut])
async def get_device_metrics(
    device_id: UUID,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Get metrics for a device within the last N hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Metric)
        .where(Metric.device_id == device_id, Metric.timestamp >= since)
        .order_by(Metric.timestamp.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/device/{device_id}/avg")
async def get_device_avg_metrics(
    device_id: UUID,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Average metrics for a device over a time period."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(
            func.avg(Metric.latency_ms).label("avg_latency_ms"),
            func.avg(Metric.packet_loss_pct).label("avg_packet_loss_pct"),
            func.avg(Metric.cpu_usage_pct).label("avg_cpu_usage_pct"),
            func.avg(Metric.memory_usage_pct).label("avg_memory_usage_pct"),
            func.count(Metric.id).label("sample_count"),
        ).where(Metric.device_id == device_id, Metric.timestamp >= since)
    )
    row = result.one()
    return {
        "device_id": str(device_id),
        "period_hours": hours,
        "avg_latency_ms": round(row.avg_latency_ms, 2) if row.avg_latency_ms else None,
        "avg_packet_loss_pct": round(row.avg_packet_loss_pct, 2) if row.avg_packet_loss_pct else None,
        "avg_cpu_usage_pct": round(row.avg_cpu_usage_pct, 2) if row.avg_cpu_usage_pct else None,
        "avg_memory_usage_pct": round(row.avg_memory_usage_pct, 2) if row.avg_memory_usage_pct else None,
        "sample_count": row.sample_count,
    }
