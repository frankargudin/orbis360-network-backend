"""Service health checker — HTTP, DNS, SMTP, TCP port checks."""

import asyncio
import logging
import socket
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ServiceResult:
    ok: bool
    response_ms: float
    error: str | None = None


async def check_http(url: str, expected_status: int = 200, timeout: int = 5) -> ServiceResult:
    """Check HTTP/HTTPS endpoint."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            resp = await client.get(url, timeout=timeout)
            elapsed = (time.monotonic() - start) * 1000
            ok = resp.status_code == expected_status if expected_status else resp.status_code < 400
            return ServiceResult(ok=ok, response_ms=round(elapsed, 1),
                                 error=None if ok else f"HTTP {resp.status_code}")
    except Exception as e:
        return ServiceResult(ok=False, response_ms=(time.monotonic() - start) * 1000, error=str(e)[:200])


async def check_tcp(host: str, port: int, timeout: int = 5) -> ServiceResult:
    """Check if a TCP port is open."""
    start = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        elapsed = (time.monotonic() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return ServiceResult(ok=True, response_ms=round(elapsed, 1))
    except Exception as e:
        return ServiceResult(ok=False, response_ms=(time.monotonic() - start) * 1000, error=str(e)[:200])


async def check_dns(hostname: str, timeout: int = 5) -> ServiceResult:
    """Check DNS resolution."""
    start = time.monotonic()
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.getaddrinfo(hostname, None), timeout=timeout
        )
        elapsed = (time.monotonic() - start) * 1000
        return ServiceResult(ok=True, response_ms=round(elapsed, 1))
    except Exception as e:
        return ServiceResult(ok=False, response_ms=(time.monotonic() - start) * 1000, error=str(e)[:200])


async def check_smtp(host: str, port: int = 25, timeout: int = 5) -> ServiceResult:
    """Check SMTP by connecting and reading banner."""
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        banner = await asyncio.wait_for(reader.readline(), timeout=timeout)
        elapsed = (time.monotonic() - start) * 1000
        writer.close()
        await writer.wait_closed()
        ok = banner.startswith(b"220")
        return ServiceResult(ok=ok, response_ms=round(elapsed, 1),
                             error=None if ok else f"Bad banner: {banner.decode()[:50]}")
    except Exception as e:
        return ServiceResult(ok=False, response_ms=(time.monotonic() - start) * 1000, error=str(e)[:200])


async def run_service_check(check_type: str, target: str, port: int | None = None,
                            expected_status: int | None = None, timeout: int = 5) -> ServiceResult:
    """Route to the appropriate checker based on type."""
    match check_type:
        case "http" | "https":
            url = target if target.startswith("http") else f"{check_type}://{target}"
            return await check_http(url, expected_status or 200, timeout)
        case "tcp":
            return await check_tcp(target, port or 80, timeout)
        case "dns":
            return await check_dns(target, timeout)
        case "smtp":
            return await check_smtp(target, port or 25, timeout)
        case _:
            return ServiceResult(ok=False, response_ms=0, error=f"Tipo de check no soportado: {check_type}")
