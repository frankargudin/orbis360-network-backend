"""SLA and availability reports."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import Device, Incident, IncidentStatus, Metric
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


@router.get("/availability")
async def availability_report(
    hours: int = Query(720, ge=1, le=8760),  # default 30 days
    db: AsyncSession = Depends(get_db),
):
    """Calculate availability (uptime %) for all devices over a time period."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    total_minutes = hours * 60

    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()

    report = []
    for device in devices:
        # Calculate downtime from resolved incidents
        incidents_result = await db.execute(
            select(Incident).where(
                Incident.device_id == device.id,
                Incident.detected_at >= since,
            )
        )
        incidents = incidents_result.scalars().all()

        downtime_minutes = 0
        for inc in incidents:
            start = max(inc.detected_at, since)
            end = inc.resolved_at or datetime.now(timezone.utc)
            delta = (end - start).total_seconds() / 60
            downtime_minutes += max(delta, 0)

        uptime_pct = max(0, ((total_minutes - downtime_minutes) / total_minutes) * 100) if total_minutes > 0 else 100
        sla_met = uptime_pct >= 99.9

        # Count metrics in period
        metric_count = await db.execute(
            select(func.count(Metric.id)).where(
                Metric.device_id == device.id,
                Metric.timestamp >= since,
            )
        )

        # Avg latency
        avg_latency = await db.execute(
            select(func.avg(Metric.latency_ms)).where(
                Metric.device_id == device.id,
                Metric.timestamp >= since,
            )
        )

        report.append({
            "device_id": str(device.id),
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "device_type": device.device_type.value,
            "is_critical": device.is_critical,
            "status": device.status.value,
            "uptime_pct": round(uptime_pct, 3),
            "downtime_minutes": round(downtime_minutes, 1),
            "incidents_count": len(incidents),
            "sla_met": sla_met,
            "metric_samples": metric_count.scalar() or 0,
            "avg_latency_ms": round(avg_latency.scalar() or 0, 2),
        })

    # Sort by uptime ascending (worst first)
    report.sort(key=lambda r: r["uptime_pct"])

    return {
        "period_hours": hours,
        "period_start": since.isoformat(),
        "total_devices": len(devices),
        "devices_meeting_sla": sum(1 for r in report if r["sla_met"]),
        "overall_availability": round(sum(r["uptime_pct"] for r in report) / max(len(report), 1), 3),
        "devices": report,
    }
