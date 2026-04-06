"""Pydantic schemas for API request/response serialization."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ─── Location ───────────────────────────────────────────────────────────────────


class LocationBase(BaseModel):
    name: str
    building: str
    floor: str | None = None
    area: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class LocationCreate(LocationBase):
    pass


class LocationOut(LocationBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


# ─── Device ─────────────────────────────────────────────────────────────────────


class DeviceBase(BaseModel):
    hostname: str
    ip_address: str
    mac_address: str | None = None
    device_type: str
    vendor: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    snmp_community: str | None = None
    snmp_port: int = 161
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_port: int = 22
    is_critical: bool = False
    location_id: UUID | None = None
    parent_device_id: UUID | None = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    hostname: str | None = None
    ip_address: str | None = None
    device_type: str | None = None
    status: str | None = None
    vendor: str | None = None
    model: str | None = None
    is_critical: bool | None = None
    location_id: UUID | None = None
    parent_device_id: UUID | None = None
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_port: int | None = None


class DeviceOut(DeviceBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    consecutive_failures: int
    last_seen: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Link ───────────────────────────────────────────────────────────────────────


class LinkBase(BaseModel):
    source_device_id: UUID
    target_device_id: UUID
    source_port: str | None = None
    target_port: str | None = None
    link_type: str
    bandwidth_mbps: int | None = None
    description: str | None = None


class LinkCreate(LinkBase):
    pass


class LinkOut(LinkBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    created_at: datetime


# ─── Metric ─────────────────────────────────────────────────────────────────────


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    device_id: UUID
    timestamp: datetime
    latency_ms: float | None
    packet_loss_pct: float | None
    cpu_usage_pct: float | None
    memory_usage_pct: float | None
    uptime_seconds: int | None


# ─── Incident ───────────────────────────────────────────────────────────────────


class IncidentCreate(BaseModel):
    title: str
    description: str | None = None
    severity: str
    device_id: UUID | None = None
    link_id: UUID | None = None


class IncidentUpdate(BaseModel):
    status: str | None = None
    resolution_notes: str | None = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    severity: str
    status: str
    device_id: UUID | None
    link_id: UUID | None
    root_cause_device_id: UUID | None
    affected_device_ids: list | None
    detected_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None


# ─── Auth ───────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str | None = None
    role: str = "technician"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    email: str
    full_name: str | None
    role: str
    is_active: bool


# ─── RCA ────────────────────────────────────────────────────────────────────────


class RCAResultOut(BaseModel):
    root_cause_device_id: UUID
    root_cause_hostname: str
    confidence: float
    affected_device_ids: list[UUID]
    reasoning: str


# ─── Alert Thresholds ──────────────────────────────────────────────────────────


class ThresholdCreate(BaseModel):
    device_id: UUID
    metric_name: str  # latency_ms, packet_loss_pct, cpu_usage_pct, memory_usage_pct
    warning_value: float | None = None
    critical_value: float | None = None
    enabled: bool = True


class ThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    device_id: UUID
    metric_name: str
    warning_value: float | None
    critical_value: float | None
    enabled: bool


# ─── SSH / Reboot ──────────────────────────────────────────────────────────────


class RebootRequest(BaseModel):
    confirm: bool = False


class RebootResponse(BaseModel):
    success: bool
    device_id: UUID
    hostname: str
    command_sent: str
    output: str
    error: str | None = None


# ─── WebSocket Events ──────────────────────────────────────────────────────────


class WSEvent(BaseModel):
    event: str  # "device_status_change", "new_incident", "metric_update", "rca_result"
    data: dict
