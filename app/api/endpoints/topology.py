"""Topology and RCA endpoints — provides the full network graph for visualization."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import Device, Link
from app.domain.services.rca_engine import RCAEngine
from app.infrastructure.database.session import get_db
from app.schemas.network import RCAResultOut

router = APIRouter(prefix="/topology", tags=["topology"], dependencies=[Depends(get_current_user)])


@router.get("")
async def get_topology(db: AsyncSession = Depends(get_db)):
    """Return full topology graph: nodes (devices) + edges (links) for Cytoscape.js."""
    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()

    links_result = await db.execute(select(Link))
    links = links_result.scalars().all()

    nodes = [
        {
            "data": {
                "id": str(d.id),
                "label": d.hostname,
                "ip": d.ip_address,
                "type": d.device_type.value,
                "status": d.status.value,
                "is_critical": d.is_critical,
                "location_id": str(d.location_id) if d.location_id else None,
            }
        }
        for d in devices
    ]

    edges = [
        {
            "data": {
                "id": str(l.id),
                "source": str(l.source_device_id),
                "target": str(l.target_device_id),
                "link_type": l.link_type.value,
                "status": l.status.value,
                "bandwidth": l.bandwidth_mbps,
            }
        }
        for l in links
    ]

    return {"nodes": nodes, "edges": edges}


@router.post("/rca", response_model=list[RCAResultOut])
async def run_rca(device_ids: list[UUID] | None = None, db: AsyncSession = Depends(get_db)):
    """Run Root Cause Analysis on currently DOWN devices (or provided list)."""
    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()

    links_result = await db.execute(select(Link))
    links = links_result.scalars().all()

    engine = RCAEngine()
    engine.build_topology(
        [
            {
                "id": d.id,
                "hostname": d.hostname,
                "device_type": d.device_type.value,
                "status": d.status.value,
                "is_critical": d.is_critical,
                "parent_device_id": d.parent_device_id,
            }
            for d in devices
        ],
        [{"source_device_id": l.source_device_id, "target_device_id": l.target_device_id} for l in links],
    )

    if device_ids:
        down_ids = device_ids
    else:
        down_ids = [d.id for d in devices if d.status.value == "down"]

    results = engine.find_root_causes(down_ids)
    return [
        RCAResultOut(
            root_cause_device_id=r.root_cause_device_id,
            root_cause_hostname=r.root_cause_hostname,
            confidence=r.confidence,
            affected_device_ids=r.affected_device_ids,
            reasoning=r.reasoning,
        )
        for r in results
    ]
