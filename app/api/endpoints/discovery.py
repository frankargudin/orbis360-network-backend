"""Network auto-discovery endpoint.

Scans an IP range using ping + SNMP to find active devices.
Returns a list of discovered devices that can be registered.
"""

import asyncio
import ipaddress
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import require_role
from app.infrastructure.monitoring.ping import ping_host
from app.infrastructure.snmp.client import SNMPClient, OID_SYS_NAME, OID_SYS_DESCR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery", tags=["discovery"], dependencies=[Depends(require_role("operator"))])


class DiscoveryRequest(BaseModel):
    network: str  # e.g., "192.168.1.0/24" or "10.0.0.1-10.0.0.50"
    snmp_community: str = "public"
    snmp_port: int = 161
    timeout: int = 2


class DiscoveredDevice(BaseModel):
    ip_address: str
    hostname: str | None = None
    description: str | None = None
    reachable_ping: bool = False
    reachable_snmp: bool = False


class DiscoveryResponse(BaseModel):
    scanned: int
    found: int
    devices: list[DiscoveredDevice]


@router.post("", response_model=DiscoveryResponse)
async def discover_network(body: DiscoveryRequest):
    """Scan a network range and return discovered devices."""
    ips = _parse_ip_range(body.network)
    if not ips:
        return DiscoveryResponse(scanned=0, found=0, devices=[])

    # Limit to 256 IPs max to prevent abuse
    ips = ips[:256]

    snmp = SNMPClient(community=body.snmp_community, timeout=body.timeout, retries=1)
    tasks = [_probe_host(ip, snmp, body.snmp_port) for ip in ips]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    devices = [r for r in results if isinstance(r, DiscoveredDevice) and (r.reachable_ping or r.reachable_snmp)]

    return DiscoveryResponse(scanned=len(ips), found=len(devices), devices=devices)


async def _probe_host(ip: str, snmp: SNMPClient, snmp_port: int) -> DiscoveredDevice:
    """Probe a single IP with ping + SNMP."""
    device = DiscoveredDevice(ip_address=ip)

    # Ping
    ping_result = await ping_host(ip, count=1, timeout=1)
    device.reachable_ping = ping_result["reachable"]

    # SNMP
    try:
        name_result = await snmp.get(ip, OID_SYS_NAME, snmp_port)
        desc_result = await snmp.get(ip, OID_SYS_DESCR, snmp_port)
        device.reachable_snmp = name_result.success
        if name_result.success:
            device.hostname = name_result.value
        if desc_result.success:
            device.description = desc_result.value
    except Exception:
        pass

    return device


def _parse_ip_range(network: str) -> list[str]:
    """Parse network string into list of IPs.
    Supports: '192.168.1.0/24', '10.0.0.1-10.0.0.50', '192.168.1.1'
    """
    try:
        # Try CIDR notation
        if "/" in network:
            net = ipaddress.ip_network(network, strict=False)
            return [str(ip) for ip in net.hosts()]

        # Try range notation
        if "-" in network:
            start_str, end_str = network.split("-", 1)
            start = ipaddress.ip_address(start_str.strip())
            end = ipaddress.ip_address(end_str.strip())
            ips = []
            current = start
            while current <= end:
                ips.append(str(current))
                current = ipaddress.ip_address(int(current) + 1)
            return ips

        # Single IP
        return [str(ipaddress.ip_address(network.strip()))]

    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid network range: {network} — {e}")
        return []
