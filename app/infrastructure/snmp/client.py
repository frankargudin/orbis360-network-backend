"""SNMP client for polling network devices.

Uses pysnmp for async SNMP v2c queries.
Key OIDs:
  - sysUpTime:    1.3.6.1.2.1.1.3.0
  - sysDescr:     1.3.6.1.2.1.1.1.0
  - sysName:      1.3.6.1.2.1.1.5.0
  - ifInOctets:   1.3.6.1.2.1.2.2.1.10
  - ifOutOctets:  1.3.6.1.2.1.2.2.1.16
  - ifOperStatus: 1.3.6.1.2.1.2.2.1.8
  - hrProcessorLoad: 1.3.6.1.2.1.25.3.3.1.2 (CPU)
"""

import logging
from dataclasses import dataclass

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    bulkCmd,
)

logger = logging.getLogger(__name__)

# Common OIDs
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"


@dataclass
class SNMPResult:
    oid: str
    value: str
    success: bool
    error: str | None = None


class SNMPClient:
    """Async SNMP client for querying network devices."""

    def __init__(self, community: str = "public", timeout: int = 5, retries: int = 2):
        self.community = community
        self.timeout = timeout
        self.retries = retries
        self.engine = SnmpEngine()

    async def get(self, host: str, oid: str, port: int = 161) -> SNMPResult:
        """SNMP GET for a single OID."""
        try:
            error_indication, error_status, error_index, var_binds = await getCmd(
                self.engine,
                CommunityData(self.community),
                UdpTransportTarget((host, port), timeout=self.timeout, retries=self.retries),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )

            if error_indication:
                return SNMPResult(oid=oid, value="", success=False, error=str(error_indication))
            if error_status:
                return SNMPResult(
                    oid=oid,
                    value="",
                    success=False,
                    error=f"{error_status.prettyPrint()} at {var_binds[int(error_index) - 1][0] if error_index else '?'}",
                )

            name, val = var_binds[0]
            return SNMPResult(oid=str(name), value=str(val), success=True)

        except Exception as e:
            logger.error(f"SNMP GET failed for {host}:{port} OID {oid}: {e}")
            return SNMPResult(oid=oid, value="", success=False, error=str(e))

    async def get_bulk(self, host: str, oid: str, port: int = 161, max_repetitions: int = 25) -> list[SNMPResult]:
        """SNMP GETBULK for walking a subtree (e.g., all interfaces)."""
        results = []
        try:
            error_indication, error_status, error_index, var_binds_table = await bulkCmd(
                self.engine,
                CommunityData(self.community),
                UdpTransportTarget((host, port), timeout=self.timeout, retries=self.retries),
                ContextData(),
                0,
                max_repetitions,
                ObjectType(ObjectIdentity(oid)),
            )

            if error_indication or error_status:
                return [SNMPResult(oid=oid, value="", success=False, error=str(error_indication or error_status))]

            for name, val in var_binds_table:
                if not str(name).startswith(oid):
                    break
                results.append(SNMPResult(oid=str(name), value=str(val), success=True))

        except Exception as e:
            logger.error(f"SNMP BULK failed for {host}: {e}")
            results.append(SNMPResult(oid=oid, value="", success=False, error=str(e)))

        return results

    async def poll_device(self, host: str, port: int = 161) -> dict:
        """Poll standard metrics from a device."""
        uptime = await self.get(host, OID_SYS_UPTIME, port)
        sys_name = await self.get(host, OID_SYS_NAME, port)
        sys_descr = await self.get(host, OID_SYS_DESCR, port)

        return {
            "reachable": uptime.success,
            "uptime": uptime.value if uptime.success else None,
            "sys_name": sys_name.value if sys_name.success else None,
            "sys_descr": sys_descr.value if sys_descr.success else None,
        }
