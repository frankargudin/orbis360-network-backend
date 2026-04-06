-- Orbis360 Network Monitor — PostgreSQL Schema
-- This runs automatically on first Docker Compose up

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Locations ──────────────────────────────────────────────────────────────────

CREATE TABLE locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    building VARCHAR(255) NOT NULL,
    floor VARCHAR(50),
    area VARCHAR(255),
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_locations_building_floor ON locations(building, floor);

-- ─── Devices ────────────────────────────────────────────────────────────────────

CREATE TYPE device_type AS ENUM ('router', 'switch', 'access_point', 'firewall', 'server', 'ups');
CREATE TYPE device_status AS ENUM ('up', 'down', 'degraded', 'unknown', 'maintenance');

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hostname VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45) UNIQUE NOT NULL,
    mac_address VARCHAR(17),
    device_type device_type NOT NULL,
    status device_status NOT NULL DEFAULT 'unknown',
    vendor VARCHAR(100),
    model VARCHAR(100),
    firmware_version VARCHAR(100),
    snmp_community VARCHAR(100),
    snmp_port INTEGER DEFAULT 161,
    is_critical BOOLEAN DEFAULT FALSE,
    consecutive_failures INTEGER DEFAULT 0,
    last_seen TIMESTAMPTZ,
    metadata_json JSONB,
    location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
    parent_device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_devices_status ON devices(status);
CREATE INDEX ix_devices_type ON devices(device_type);
CREATE INDEX ix_devices_location ON devices(location_id);
CREATE INDEX ix_devices_parent ON devices(parent_device_id);

-- ─── Links ──────────────────────────────────────────────────────────────────────

CREATE TYPE link_type AS ENUM ('fiber', 'copper', 'wireless', 'virtual');
CREATE TYPE link_status AS ENUM ('active', 'down', 'degraded');

CREATE TABLE links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    target_device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    source_port VARCHAR(50),
    target_port VARCHAR(50),
    link_type link_type NOT NULL,
    status link_status NOT NULL DEFAULT 'active',
    bandwidth_mbps INTEGER,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_links_source ON links(source_device_id);
CREATE INDEX ix_links_target ON links(target_device_id);
CREATE INDEX ix_links_status ON links(status);

-- ─── Metrics (time-series) ──────────────────────────────────────────────────────

CREATE TABLE metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    latency_ms DOUBLE PRECISION,
    packet_loss_pct DOUBLE PRECISION,
    cpu_usage_pct DOUBLE PRECISION,
    memory_usage_pct DOUBLE PRECISION,
    interface_in_octets INTEGER,
    interface_out_octets INTEGER,
    uptime_seconds INTEGER,
    snmp_data JSONB
);

CREATE INDEX ix_metrics_device_ts ON metrics(device_id, timestamp);
CREATE INDEX ix_metrics_ts ON metrics(timestamp);

-- ─── Incidents ──────────────────────────────────────────────────────────────────

CREATE TYPE incident_severity AS ENUM ('critical', 'major', 'minor', 'warning');
CREATE TYPE incident_status AS ENUM ('open', 'acknowledged', 'resolved');

CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity incident_severity NOT NULL,
    status incident_status NOT NULL DEFAULT 'open',
    device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    link_id UUID REFERENCES links(id) ON DELETE SET NULL,
    root_cause_device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    affected_device_ids JSONB,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_incidents_status ON incidents(status);
CREATE INDEX ix_incidents_severity ON incidents(severity);
CREATE INDEX ix_incidents_device ON incidents(device_id);
CREATE INDEX ix_incidents_detected ON incidents(detected_at);

-- ─── Users ──────────────────────────────────────────────────────────────────────

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'technician',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Seed Data ──────────────────────────────────────────────────────────────────

-- Default admin user (password: admin123)
INSERT INTO users (username, email, hashed_password, full_name, role)
VALUES ('admin', 'admin@orbis360.local', '$2b$12$LJ3m4ys3Lz0jKzYNEMC8/.ByNDEtA/0Y0fRGBwqXTvCJ1V3J5K8.q', 'System Admin', 'admin');

-- Sample building location
INSERT INTO locations (id, name, building, floor, area) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Edificio Principal - Piso 1', 'Torre A', '1', 'Networking'),
    ('a0000000-0000-0000-0000-000000000002', 'Edificio Principal - Piso 2', 'Torre A', '2', 'Oficinas'),
    ('a0000000-0000-0000-0000-000000000003', 'Edificio Principal - Piso 3', 'Torre A', '3', 'Servidores');

-- Sample network topology
INSERT INTO devices (id, hostname, ip_address, device_type, status, vendor, model, is_critical, location_id) VALUES
    ('d0000000-0000-0000-0000-000000000001', 'core-router-01', '10.0.0.1', 'router', 'up', 'Cisco', 'ISR 4451', TRUE, 'a0000000-0000-0000-0000-000000000001'),
    ('d0000000-0000-0000-0000-000000000002', 'core-switch-01', '10.0.0.2', 'switch', 'up', 'Cisco', 'Catalyst 9300', TRUE, 'a0000000-0000-0000-0000-000000000001'),
    ('d0000000-0000-0000-0000-000000000003', 'dist-switch-f2', '10.0.2.1', 'switch', 'up', 'Cisco', 'Catalyst 3850', FALSE, 'a0000000-0000-0000-0000-000000000002'),
    ('d0000000-0000-0000-0000-000000000004', 'dist-switch-f3', '10.0.3.1', 'switch', 'up', 'Cisco', 'Catalyst 3850', FALSE, 'a0000000-0000-0000-0000-000000000003'),
    ('d0000000-0000-0000-0000-000000000005', 'ap-f2-01', '10.0.2.10', 'access_point', 'up', 'Ubiquiti', 'U6-Pro', FALSE, 'a0000000-0000-0000-0000-000000000002'),
    ('d0000000-0000-0000-0000-000000000006', 'ap-f2-02', '10.0.2.11', 'access_point', 'up', 'Ubiquiti', 'U6-Pro', FALSE, 'a0000000-0000-0000-0000-000000000002'),
    ('d0000000-0000-0000-0000-000000000007', 'ap-f3-01', '10.0.3.10', 'access_point', 'up', 'Ubiquiti', 'U6-LR', FALSE, 'a0000000-0000-0000-0000-000000000003'),
    ('d0000000-0000-0000-0000-000000000008', 'firewall-01', '10.0.0.254', 'firewall', 'up', 'Fortinet', 'FortiGate 100F', TRUE, 'a0000000-0000-0000-0000-000000000001'),
    ('d0000000-0000-0000-0000-000000000009', 'server-dc-01', '10.0.3.100', 'server', 'up', 'Dell', 'PowerEdge R740', TRUE, 'a0000000-0000-0000-0000-000000000003');

-- Set parent relationships (topology hierarchy)
UPDATE devices SET parent_device_id = 'd0000000-0000-0000-0000-000000000001' WHERE id = 'd0000000-0000-0000-0000-000000000002';
UPDATE devices SET parent_device_id = 'd0000000-0000-0000-0000-000000000002' WHERE id IN ('d0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000004');
UPDATE devices SET parent_device_id = 'd0000000-0000-0000-0000-000000000003' WHERE id IN ('d0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000006');
UPDATE devices SET parent_device_id = 'd0000000-0000-0000-0000-000000000004' WHERE id = 'd0000000-0000-0000-0000-000000000007';
UPDATE devices SET parent_device_id = 'd0000000-0000-0000-0000-000000000001' WHERE id = 'd0000000-0000-0000-0000-000000000008';
UPDATE devices SET parent_device_id = 'd0000000-0000-0000-0000-000000000004' WHERE id = 'd0000000-0000-0000-0000-000000000009';

-- Links (physical connections)
INSERT INTO links (source_device_id, target_device_id, source_port, target_port, link_type, bandwidth_mbps, description) VALUES
    ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 'Gi0/0', 'Te1/0/1', 'fiber', 10000, 'Core router to core switch - 10G fiber'),
    ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000008', 'Gi0/1', 'port1', 'fiber', 10000, 'Core router to firewall'),
    ('d0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'Te1/0/2', 'Te1/0/1', 'fiber', 10000, 'Core switch to floor 2 distribution'),
    ('d0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000004', 'Te1/0/3', 'Te1/0/1', 'fiber', 10000, 'Core switch to floor 3 distribution'),
    ('d0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000005', 'Gi1/0/1', 'eth0', 'copper', 1000, 'Floor 2 switch to AP-01'),
    ('d0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000006', 'Gi1/0/2', 'eth0', 'copper', 1000, 'Floor 2 switch to AP-02'),
    ('d0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000007', 'Gi1/0/1', 'eth0', 'copper', 1000, 'Floor 3 switch to AP-01'),
    ('d0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000009', 'Gi1/0/10', 'iDRAC', 'copper', 1000, 'Floor 3 switch to server');

-- ─── Useful Queries Reference ───────────────────────────────────────────────────
-- Devices currently down:
--   SELECT hostname, ip_address, consecutive_failures FROM devices WHERE status = 'down';
--
-- Open incidents with severity:
--   SELECT title, severity, detected_at FROM incidents WHERE status = 'open' ORDER BY detected_at DESC;
--
-- Average latency per device (last 24h):
--   SELECT d.hostname, AVG(m.latency_ms) as avg_latency
--   FROM metrics m JOIN devices d ON m.device_id = d.id
--   WHERE m.timestamp > NOW() - INTERVAL '24 hours'
--   GROUP BY d.hostname ORDER BY avg_latency DESC;
--
-- Incident count by device (top offenders):
--   SELECT d.hostname, COUNT(i.id) as incident_count
--   FROM incidents i JOIN devices d ON i.device_id = d.id
--   GROUP BY d.hostname ORDER BY incident_count DESC LIMIT 10;
--
-- Devices per building/floor:
--   SELECT l.building, l.floor, COUNT(d.id) as device_count
--   FROM devices d JOIN locations l ON d.location_id = l.id
--   GROUP BY l.building, l.floor ORDER BY l.building, l.floor;
