"""ICMP ping utility for device reachability checks.

Uses subprocess to call system ping (avoids raw socket / root requirement).
"""

import asyncio
import logging
import platform
import time

logger = logging.getLogger(__name__)


async def ping_host(host: str, count: int = 3, timeout: int = 5) -> dict:
    """Ping a host and return latency + packet loss.

    Returns:
        {
            "reachable": bool,
            "latency_ms": float | None,
            "packet_loss_pct": float,
        }
    """
    param_count = "-n" if platform.system().lower() == "windows" else "-c"
    param_timeout = "-w" if platform.system().lower() == "windows" else "-W"

    cmd = ["ping", param_count, str(count), param_timeout, str(timeout), host]

    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 5)
        elapsed = (time.monotonic() - start) * 1000
        output = stdout.decode()

        # Parse packet loss
        packet_loss = 100.0
        if "packet loss" in output.lower():
            for part in output.split():
                if "%" in part:
                    try:
                        packet_loss = float(part.strip("%").strip(","))
                        break
                    except ValueError:
                        continue

        # Parse avg latency from "min/avg/max" line
        latency = None
        if packet_loss < 100:
            for line in output.splitlines():
                if "avg" in line.lower() or "average" in line.lower():
                    parts = line.split("/")
                    if len(parts) >= 5:
                        try:
                            latency = float(parts[-3])
                        except (ValueError, IndexError):
                            latency = elapsed / count

        return {
            "reachable": packet_loss < 100,
            "latency_ms": latency,
            "packet_loss_pct": packet_loss,
        }

    except (asyncio.TimeoutError, OSError) as e:
        logger.warning(f"Ping to {host} failed: {e}")
        return {"reachable": False, "latency_ms": None, "packet_loss_pct": 100.0}
