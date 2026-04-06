"""SSH client for remote device management.

Supports reboot commands per device type:
  - Cisco IOS/IOS-XE: "reload\n\ny\n"
  - Linux/Server:      "sudo reboot"
  - Ubiquiti UniFi:    "reboot"
  - FortiGate:         "execute reboot"
  - Generic:           "reboot"

Security notes:
  - Passwords are stored in DB (should be encrypted at rest in production)
  - SSH host key verification is disabled for lab environments
  - In production, use known_hosts or a vault service
"""

import asyncio
import logging
from dataclasses import dataclass

import asyncssh

logger = logging.getLogger(__name__)

# Reboot commands per device type and vendor
REBOOT_COMMANDS: dict[str, dict[str, str]] = {
    "router": {
        "cisco": "reload\n",
        "juniper": "request system reboot",
        "mikrotik": "/system reboot\ny",
        "_default": "reload\n",
    },
    "switch": {
        "cisco": "reload\n",
        "juniper": "request system reboot",
        "mikrotik": "/system reboot\ny",
        "_default": "reload\n",
    },
    "access_point": {
        "ubiquiti": "reboot",
        "cisco": "reload\n",
        "_default": "reboot",
    },
    "firewall": {
        "fortinet": "execute reboot\ny",
        "paloalto": "request restart system",
        "cisco": "reload\n",
        "_default": "reboot",
    },
    "server": {
        "_default": "sudo reboot",
    },
    "ups": {
        "_default": "echo 'UPS reboot not supported via SSH'",
    },
}


@dataclass
class SSHResult:
    success: bool
    command: str
    output: str
    error: str | None = None


class SSHClient:
    """Async SSH client for executing commands on network devices."""

    @staticmethod
    def get_reboot_command(device_type: str, vendor: str | None) -> str:
        """Determine the correct reboot command for a device."""
        type_commands = REBOOT_COMMANDS.get(device_type, REBOOT_COMMANDS["server"])
        if vendor:
            vendor_lower = vendor.lower()
            for key, cmd in type_commands.items():
                if key != "_default" and key in vendor_lower:
                    return cmd
        return type_commands.get("_default", "reboot")

    @staticmethod
    async def execute(
        host: str,
        username: str,
        password: str,
        command: str,
        port: int = 22,
        timeout: int = 30,
    ) -> SSHResult:
        """Execute a command on a remote device via SSH."""
        try:
            async with asyncssh.connect(
                host,
                port=port,
                username=username,
                password=password,
                known_hosts=None,  # Disable host key checking (lab/enterprise with internal CA)
                connect_timeout=timeout,
            ) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False),
                    timeout=timeout,
                )
                output = (result.stdout or "") + (result.stderr or "")
                return SSHResult(
                    success=result.exit_status == 0 or result.exit_status is None,
                    command=command,
                    output=output.strip() if output else "Comando enviado correctamente",
                )

        except asyncssh.PermissionDenied:
            logger.error(f"SSH auth failed for {username}@{host}:{port}")
            return SSHResult(success=False, command=command, output="", error="Autenticación fallida — verifica usuario y contraseña")

        except asyncssh.ConnectionLost:
            # Connection lost after reboot command is expected behavior
            logger.info(f"SSH connection lost to {host} after reboot command — expected")
            return SSHResult(success=True, command=command, output="Conexión cerrada por el dispositivo — reinicio en progreso")

        except (OSError, asyncssh.Error) as e:
            logger.error(f"SSH connection to {host}:{port} failed: {e}")
            return SSHResult(success=False, command=command, output="", error=f"No se pudo conectar: {e}")

        except asyncio.TimeoutError:
            # Timeout after sending reboot is also expected
            logger.info(f"SSH timeout for {host} after reboot — expected")
            return SSHResult(success=True, command=command, output="Tiempo de espera agotado — el dispositivo probablemente está reiniciando")

    @staticmethod
    async def reboot_device(
        host: str,
        username: str,
        password: str,
        device_type: str,
        vendor: str | None = None,
        port: int = 22,
    ) -> SSHResult:
        """Reboot a device using the appropriate command for its type."""
        command = SSHClient.get_reboot_command(device_type, vendor)
        logger.info(f"Rebooting {host} (type={device_type}, vendor={vendor}) with command: {command}")
        return await SSHClient.execute(host, username, password, command, port)
