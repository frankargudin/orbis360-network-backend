"""Background monitoring worker.

Runs periodic health checks using ping + SNMP, updates device status,
records metrics, detects outages, triggers RCA, and broadcasts events via WebSocket.

False Positive Prevention Strategy:
1. Consecutive failure threshold (default=3) before marking DOWN
2. SNMP validation after ping failure (device may block ICMP)
3. Link status inferred from both endpoints
4. Automatic recovery detection
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.events import ws_manager
from app.domain.models.network import (
    AlertThreshold,
    Device,
    DeviceStatus,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    Link,
    MaintenanceWindow,
    LinkStatus,
    Metric,
)
from app.domain.services.rca_engine import RCAEngine
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.monitoring.ping import ping_host
from app.infrastructure.snmp.client import SNMPClient

logger = logging.getLogger(__name__)
settings = get_settings()


class NetworkMonitorWorker:
    """Orchestrates periodic monitoring of all devices."""

    def __init__(self):
        self.snmp_client = SNMPClient(
            community=settings.SNMP_COMMUNITY,
            timeout=settings.SNMP_TIMEOUT,
            retries=settings.SNMP_RETRIES,
        )
        self.rca_engine = RCAEngine()
        self._running = False

    async def start(self):
        """Start the monitoring loop."""
        self._running = True
        logger.info("Network monitor worker started")
        while self._running:
            try:
                await self._monitor_cycle()
            except Exception as e:
                logger.error(f"Monitor cycle error: {e}", exc_info=True)
            await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL_SECONDS)

    async def stop(self):
        self._running = False
        logger.info("Network monitor worker stopped")

    async def _monitor_cycle(self):
        """Single monitoring cycle: check → propagate → links → RCA."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Device).where(Device.status != DeviceStatus.MAINTENANCE)
            )
            devices = result.scalars().all()
            if not devices:
                return

            # Build device map for ancestor checks
            device_map = {d.id: d for d in devices}

            # Step 1: Check all devices concurrently (ping + SNMP)
            await asyncio.gather(
                *[self._check_device(session, device, device_map) for device in devices],
                return_exceptions=True,
            )
            await session.commit()

            # Step 2: Propagate — if parent is DOWN, children are DOWN too
            # Re-fetch fresh state after checks
            result = await session.execute(
                select(Device).where(Device.status != DeviceStatus.MAINTENANCE)
            )
            devices = result.scalars().all()
            await self._propagate_parent_failures(session, devices)
            await session.commit()

            # Step 3: Update link statuses
            await self._update_link_statuses(session)
            await session.commit()

            # Step 4: RCA
            result = await session.execute(
                select(Device).where(Device.status != DeviceStatus.MAINTENANCE)
            )
            devices = result.scalars().all()
            await self._run_rca_if_needed(session, devices)

    async def _is_in_maintenance(self, session: AsyncSession, device_id) -> bool:
        """Check if device has an active maintenance window right now."""
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(MaintenanceWindow).where(
                MaintenanceWindow.device_id == device_id,
                MaintenanceWindow.start_time <= now,
                MaintenanceWindow.end_time >= now,
            )
        )
        return result.scalar_one_or_none() is not None

    def _is_ancestor_down(self, device_id, device_map: dict) -> bool:
        """Walk up the parent chain. If any ancestor is DOWN, return True."""
        visited = set()
        current_id = device_map.get(device_id)
        if current_id:
            current_id = current_id.parent_device_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            parent = device_map.get(current_id)
            if not parent:
                break
            if parent.status == DeviceStatus.DOWN:
                return True
            current_id = parent.parent_device_id
        return False

    async def _check_device(self, session: AsyncSession, device: Device, device_map: dict = None):
        """Check a single device with ping + SNMP, apply consecutive failure logic."""
        # Step 1: Ping (fast: 1 packet, 2s timeout)
        ping_result = await ping_host(device.ip_address, count=1, timeout=2)

        # Step 2: SNMP (authoritative — validates the actual service is running)
        community = device.snmp_community or settings.SNMP_COMMUNITY
        snmp_client = SNMPClient(community=community, timeout=settings.SNMP_TIMEOUT, retries=settings.SNMP_RETRIES)
        snmp_result = await snmp_client.poll_device(
            device.ip_address, device.snmp_port
        )

        # If SNMP port is non-standard (simulation), SNMP is the authority.
        # If SNMP port is 161 (real device), use both ping OR SNMP.
        if device.snmp_port != 161:
            is_reachable = snmp_result["reachable"]
        else:
            is_reachable = ping_result["reachable"] or snmp_result["reachable"]

        now = datetime.now(timezone.utc)

        previous_status = device.status

        # Even if SNMP responds, if an ancestor is DOWN this device is unreachable in reality
        if is_reachable and device_map and self._is_ancestor_down(device.id, device_map):
            is_reachable = False

        # If device is in a maintenance window, mark as maintenance and skip alerts
        if await self._is_in_maintenance(session, device.id):
            if device.status != DeviceStatus.MAINTENANCE:
                device.status = DeviceStatus.MAINTENANCE
                device.consecutive_failures = 0
                session.add(device)
            return

        if is_reachable:
            # Device is UP — reset failure counter
            device.consecutive_failures = 0
            device.status = DeviceStatus.UP
            device.last_seen = now

            # Record metric
            metric = Metric(
                device_id=device.id,
                timestamp=now,
                latency_ms=ping_result.get("latency_ms"),
                packet_loss_pct=ping_result.get("packet_loss_pct"),
                uptime_seconds=int(snmp_result["uptime"]) if snmp_result.get("uptime") else None,
            )
            session.add(metric)

            # Check thresholds
            await self._check_thresholds(session, device, metric, now)

            # Recovery — auto-resolve open incidents for this device
            if previous_status in (DeviceStatus.DOWN, DeviceStatus.DEGRADED):
                open_incidents = await session.execute(
                    select(Incident).where(
                        Incident.device_id == device.id,
                        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
                    )
                )
                for inc in open_incidents.scalars().all():
                    inc.status = IncidentStatus.RESOLVED
                    inc.resolved_at = now
                    inc.resolution_notes = "Resuelto automáticamente — dispositivo recuperado"
                    session.add(inc)

                await ws_manager.broadcast("device_status_change", {
                    "device_id": str(device.id),
                    "hostname": device.hostname,
                    "status": "up",
                    "previous_status": previous_status.value,
                })
        else:
            # Device unreachable — increment failure counter
            device.consecutive_failures += 1

            if device.consecutive_failures >= settings.DOWN_THRESHOLD:
                device.status = DeviceStatus.DOWN

                if previous_status != DeviceStatus.DOWN:
                    # New outage detected
                    logger.warning(f"Device DOWN: {device.hostname} ({device.ip_address})")

                    incident = Incident(
                        title=f"Device DOWN: {device.hostname}",
                        description=f"Device {device.hostname} ({device.ip_address}) unreachable after {device.consecutive_failures} consecutive checks",
                        severity=IncidentSeverity.CRITICAL if device.is_critical else IncidentSeverity.MAJOR,
                        status=IncidentStatus.OPEN,
                        device_id=device.id,
                        detected_at=now,
                    )
                    session.add(incident)

                    await ws_manager.broadcast("device_status_change", {
                        "device_id": str(device.id),
                        "hostname": device.hostname,
                        "status": "down",
                        "previous_status": previous_status.value,
                        "consecutive_failures": device.consecutive_failures,
                    })
            else:
                device.status = DeviceStatus.DEGRADED

        session.add(device)

    async def _check_thresholds(self, session: AsyncSession, device: Device, metric: Metric, now):
        """Check if any metric exceeds configured thresholds and create incidents."""
        result = await session.execute(
            select(AlertThreshold).where(
                AlertThreshold.device_id == device.id,
                AlertThreshold.enabled == True,
            )
        )
        thresholds = result.scalars().all()

        metric_values = {
            "latency_ms": metric.latency_ms,
            "packet_loss_pct": metric.packet_loss_pct,
            "cpu_usage_pct": metric.cpu_usage_pct,
            "memory_usage_pct": metric.memory_usage_pct,
        }

        metric_labels = {
            "latency_ms": "Latencia",
            "packet_loss_pct": "Pérdida de paquetes",
            "cpu_usage_pct": "CPU",
            "memory_usage_pct": "Memoria",
        }

        for threshold in thresholds:
            value = metric_values.get(threshold.metric_name)
            if value is None:
                continue

            label = metric_labels.get(threshold.metric_name, threshold.metric_name)
            severity = None

            if threshold.critical_value and value >= threshold.critical_value:
                severity = IncidentSeverity.CRITICAL
            elif threshold.warning_value and value >= threshold.warning_value:
                severity = IncidentSeverity.WARNING

            if severity:
                # Check if there's already an open threshold incident for this device+metric
                existing = await session.execute(
                    select(Incident).where(
                        Incident.device_id == device.id,
                        Incident.title.like(f"Umbral%{label}%{device.hostname}%"),
                        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
                    )
                )
                if not existing.scalar_one_or_none():
                    incident = Incident(
                        title=f"Umbral {severity.value}: {label} en {device.hostname}",
                        description=f"{label} = {value:.1f} (umbral warning: {threshold.warning_value}, critical: {threshold.critical_value})",
                        severity=severity,
                        status=IncidentStatus.OPEN,
                        device_id=device.id,
                        detected_at=now,
                    )
                    session.add(incident)

                    await ws_manager.broadcast("threshold_alert", {
                        "device_id": str(device.id),
                        "hostname": device.hostname,
                        "metric": threshold.metric_name,
                        "value": value,
                        "severity": severity.value,
                    })

    async def _propagate_parent_failures(self, session: AsyncSession, devices: list):
        """Propagate DOWN status through the parent-child tree.

        - If a parent is DOWN → all children become DOWN (cascade)
        - If a parent recovers (UP) → children that were down by dependency
          get their consecutive_failures reset so they recover on next check
        """
        device_map = {d.id: d for d in devices}
        down_ids = {d.id for d in devices if d.status == DeviceStatus.DOWN}
        up_ids = {d.id for d in devices if d.status == DeviceStatus.UP}
        now = datetime.now(timezone.utc)

        # Phase 1: Cascade DOWN — walk tree and propagate failures
        changed = True
        while changed:
            changed = False
            for device in devices:
                if device.id in down_ids:
                    continue
                if device.parent_device_id and device.parent_device_id in down_ids:
                    previous = device.status
                    device.status = DeviceStatus.DOWN
                    device.consecutive_failures = settings.DOWN_THRESHOLD
                    session.add(device)
                    down_ids.add(device.id)
                    changed = True

                    # Create incident if not already open
                    existing = await session.execute(
                        select(Incident).where(
                            Incident.device_id == device.id,
                            Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
                        )
                    )
                    if not existing.scalar_one_or_none():
                        parent = device_map.get(device.parent_device_id)
                        parent_name = parent.hostname if parent else "desconocido"
                        incident = Incident(
                            title=f"Caído por dependencia: {device.hostname}",
                            description=f"{device.hostname} inalcanzable porque su dispositivo padre ({parent_name}) está caído",
                            severity=IncidentSeverity.CRITICAL if device.is_critical else IncidentSeverity.MAJOR,
                            status=IncidentStatus.OPEN,
                            device_id=device.id,
                            detected_at=now,
                        )
                        session.add(incident)

                    await ws_manager.broadcast("device_status_change", {
                        "device_id": str(device.id),
                        "hostname": device.hostname,
                        "status": "down",
                        "reason": "parent_down",
                    })

        # Phase 2: Cascade RECOVERY — only for devices that fell by dependency
        # A device fell by dependency if: it's DOWN, its parent is now UP,
        # AND it has an open incident with "dependencia" in the title
        for device in devices:
            if device.status != DeviceStatus.DOWN or not device.parent_device_id:
                continue
            parent = device_map.get(device.parent_device_id)
            if not parent or parent.status != DeviceStatus.UP:
                continue

            # Check if this device fell by dependency (not by its own failure)
            dep_incident = await session.execute(
                select(Incident).where(
                    Incident.device_id == device.id,
                    Incident.title.like("Caído por dependencia%"),
                    Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
                )
            )
            if not dep_incident.scalar_one_or_none():
                continue  # Fell on its own — don't auto-recover

            # Parent is back and this device fell by dependency → recover it
            device.consecutive_failures = 0
            device.status = DeviceStatus.UP
            device.last_seen = now
            session.add(device)

            # Auto-resolve dependency incidents
            open_incidents = await session.execute(
                select(Incident).where(
                    Incident.device_id == device.id,
                    Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
                )
            )
            for inc in open_incidents.scalars().all():
                inc.status = IncidentStatus.RESOLVED
                inc.resolved_at = now
                inc.resolution_notes = "Resuelto — dispositivo padre recuperado"
                session.add(inc)

            await ws_manager.broadcast("device_status_change", {
                "device_id": str(device.id),
                "hostname": device.hostname,
                "status": "up",
                "reason": "parent_recovered",
            })

    async def _update_link_statuses(self, session: AsyncSession):
        """Infer link status from the status of its endpoint devices."""
        result = await session.execute(
            select(Link).join(Device, Link.source_device_id == Device.id)
        )
        links = result.scalars().all()

        for link in links:
            src = await session.get(Device, link.source_device_id)
            tgt = await session.get(Device, link.target_device_id)

            if not src or not tgt:
                continue

            previous_status = link.status

            if src.status == DeviceStatus.DOWN or tgt.status == DeviceStatus.DOWN:
                link.status = LinkStatus.DOWN
            elif src.status == DeviceStatus.DEGRADED or tgt.status == DeviceStatus.DEGRADED:
                link.status = LinkStatus.DEGRADED
            else:
                link.status = LinkStatus.ACTIVE

            if link.status != previous_status:
                await ws_manager.broadcast("link_status_change", {
                    "link_id": str(link.id),
                    "status": link.status.value,
                    "source_device_id": str(link.source_device_id),
                    "target_device_id": str(link.target_device_id),
                })

            session.add(link)

    async def _run_rca_if_needed(self, session: AsyncSession, devices):
        """Run Root Cause Analysis when multiple devices are DOWN."""
        down_devices = [d for d in devices if d.status == DeviceStatus.DOWN]

        if len(down_devices) < 2:
            return

        # Fetch links for topology
        links_result = await session.execute(select(Link))
        links = links_result.scalars().all()

        # Build topology
        device_dicts = [
            {
                "id": d.id,
                "hostname": d.hostname,
                "device_type": d.device_type.value,
                "status": d.status.value,
                "is_critical": d.is_critical,
                "parent_device_id": d.parent_device_id,
            }
            for d in devices
        ]
        link_dicts = [
            {"source_device_id": l.source_device_id, "target_device_id": l.target_device_id}
            for l in links
        ]

        self.rca_engine.build_topology(device_dicts, link_dicts)
        results = self.rca_engine.find_root_causes([d.id for d in down_devices])

        if results:
            top = results[0]
            logger.info(f"RCA: Root cause = {top.root_cause_hostname} (confidence: {top.confidence})")

            # Update open incidents with RCA
            for incident in await self._get_open_incidents(session):
                incident.root_cause_device_id = top.root_cause_device_id
                incident.affected_device_ids = [str(uid) for uid in top.affected_device_ids]
                session.add(incident)

            await session.commit()

            await ws_manager.broadcast("rca_result", {
                "root_cause_device_id": str(top.root_cause_device_id),
                "root_cause_hostname": top.root_cause_hostname,
                "confidence": top.confidence,
                "affected_count": len(top.affected_device_ids),
                "reasoning": top.reasoning,
            })

    async def _get_open_incidents(self, session: AsyncSession):
        result = await session.execute(
            select(Incident).where(Incident.status == IncidentStatus.OPEN)
        )
        return result.scalars().all()
