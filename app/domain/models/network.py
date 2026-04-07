"""Core network domain models — devices, links, locations, metrics, incidents."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


# ─── Enums ──────────────────────────────────────────────────────────────────────


class DeviceType(str, enum.Enum):
    ROUTER = "router"
    SWITCH = "switch"
    ACCESS_POINT = "access_point"
    FIREWALL = "firewall"
    SERVER = "server"
    UPS = "ups"


class DeviceStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class LinkType(str, enum.Enum):
    FIBER = "fiber"
    COPPER = "copper"
    WIRELESS = "wireless"
    VIRTUAL = "virtual"


class LinkStatus(str, enum.Enum):
    ACTIVE = "active"
    DOWN = "down"
    DEGRADED = "degraded"


class IncidentSeverity(str, enum.Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    WARNING = "warning"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# ─── Location ───────────────────────────────────────────────────────────────────


class Location(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "locations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    building: Mapped[str] = mapped_column(String(255), nullable=False)
    floor: Mapped[str | None] = mapped_column(String(50))
    area: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    devices: Mapped[list["Device"]] = relationship(back_populates="location")

    __table_args__ = (
        Index("ix_locations_building_floor", "building", "floor"),
    )


# ─── Device ─────────────────────────────────────────────────────────────────────


class Device(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "devices"

    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    mac_address: Mapped[str | None] = mapped_column(String(17))
    device_type: Mapped[DeviceType] = mapped_column(
        Enum(DeviceType, name="device_type", create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, name="device_status", create_type=False, values_callable=lambda e: [x.value for x in e]),
        default=DeviceStatus.UNKNOWN,
        nullable=False,
    )
    vendor: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    firmware_version: Mapped[str | None] = mapped_column(String(100))
    snmp_community: Mapped[str | None] = mapped_column(String(100))
    snmp_port: Mapped[int] = mapped_column(Integer, default=161)
    ssh_username: Mapped[str | None] = mapped_column(String(100))
    ssh_password: Mapped[str | None] = mapped_column(String(255))
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    is_flapping: Mapped[bool] = mapped_column(Boolean, default=False)
    flap_count: Mapped[int] = mapped_column(Integer, default=0)
    last_state_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    # Relations
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    parent_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id")
    )
    location: Mapped[Location | None] = relationship(back_populates="devices")
    parent_device: Mapped["Device | None"] = relationship(remote_side="Device.id")
    metrics: Mapped[list["Metric"]] = relationship(back_populates="device")
    source_links: Mapped[list["Link"]] = relationship(
        foreign_keys="Link.source_device_id", back_populates="source_device"
    )
    target_links: Mapped[list["Link"]] = relationship(
        foreign_keys="Link.target_device_id", back_populates="target_device"
    )

    __table_args__ = (
        Index("ix_devices_status", "status"),
        Index("ix_devices_type", "device_type"),
        Index("ix_devices_location", "location_id"),
        Index("ix_devices_parent", "parent_device_id"),
    )


# ─── Link ───────────────────────────────────────────────────────────────────────


class Link(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "links"

    source_device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    target_device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    source_port: Mapped[str | None] = mapped_column(String(50))
    target_port: Mapped[str | None] = mapped_column(String(50))
    link_type: Mapped[LinkType] = mapped_column(
        Enum(LinkType, name="link_type", create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[LinkStatus] = mapped_column(
        Enum(LinkStatus, name="link_status", create_type=False, values_callable=lambda e: [x.value for x in e]),
        default=LinkStatus.ACTIVE,
        nullable=False,
    )
    bandwidth_mbps: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)

    source_device: Mapped[Device] = relationship(
        foreign_keys=[source_device_id], back_populates="source_links"
    )
    target_device: Mapped[Device] = relationship(
        foreign_keys=[target_device_id], back_populates="target_links"
    )

    __table_args__ = (
        Index("ix_links_source", "source_device_id"),
        Index("ix_links_target", "target_device_id"),
        Index("ix_links_status", "status"),
    )


# ─── Metric ─────────────────────────────────────────────────────────────────────


class Metric(Base, UUIDMixin):
    __tablename__ = "metrics"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    latency_ms: Mapped[float | None] = mapped_column(Float)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float)
    cpu_usage_pct: Mapped[float | None] = mapped_column(Float)
    memory_usage_pct: Mapped[float | None] = mapped_column(Float)
    interface_in_octets: Mapped[int | None] = mapped_column(Integer)
    interface_out_octets: Mapped[int | None] = mapped_column(Integer)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    snmp_data: Mapped[dict | None] = mapped_column(JSONB)

    device: Mapped[Device] = relationship(back_populates="metrics")

    __table_args__ = (
        Index("ix_metrics_device_ts", "device_id", "timestamp"),
        Index("ix_metrics_ts", "timestamp"),
    )


# ─── Incident ───────────────────────────────────────────────────────────────────


class Incident(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incident_severity", create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", create_type=False, values_callable=lambda e: [x.value for x in e]),
        default=IncidentStatus.OPEN,
        nullable=False,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id")
    )
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("links.id")
    )
    root_cause_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id")
    )
    affected_device_ids: Mapped[list | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_device", "device_id"),
        Index("ix_incidents_detected", "detected_at"),
    )


# ─── Audit Log ──────────────────────────────────────────────────────────────────


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_log"

    user_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # create, update, delete, reboot, login
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # device, incident, link, etc.
    entity_id: Mapped[str | None] = mapped_column(String(255))
    entity_name: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )


# ─── Service Check ──────────────────────────────────────────────────────────────


class ServiceCheckType(str, enum.Enum):
    HTTP = "http"
    HTTPS = "https"
    DNS = "dns"
    SMTP = "smtp"
    TCP = "tcp"
    ICMP = "icmp"


class ServiceCheckStatus(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ServiceCheck(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "service_checks"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[ServiceCheckType] = mapped_column(
        Enum(ServiceCheckType, name="service_check_type", create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    expected_status: Mapped[int | None] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[ServiceCheckStatus] = mapped_column(
        Enum(ServiceCheckStatus, name="service_check_status", create_type=False, values_callable=lambda e: [x.value for x in e]),
        default=ServiceCheckStatus.UNKNOWN,
    )
    last_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_response_ms: Mapped[float | None] = mapped_column(Float)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_svc_device", "device_id"),
    )


# ─── Alert Threshold ────────────────────────────────────────────────────────────


class AlertThreshold(Base, UUIDMixin, TimestampMixin):
    """Configurable thresholds per device per metric.
    metric_name: 'latency_ms', 'packet_loss_pct', 'cpu_usage_pct', 'memory_usage_pct'
    """
    __tablename__ = "alert_thresholds"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    warning_value: Mapped[float | None] = mapped_column(Float)
    critical_value: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_thresholds_device", "device_id"),
    )


# ─── Maintenance Window ────────────────────────────────────────────────────────


class MaintenanceWindow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "maintenance_windows"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        Index("ix_maint_device", "device_id"),
        Index("ix_maint_times", "start_time", "end_time"),
    )


# ─── User ───────────────────────────────────────────────────────────────────────


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="technician")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
