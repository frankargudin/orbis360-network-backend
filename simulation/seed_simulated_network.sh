#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Orbis360 — Registrar dispositivos simulados
#
# Los dispositivos usan localhost con puertos mapeados:
#   - IP: 127.0.0.1 (para ping)
#   - SSH port: 22xx (mapeado al contenedor)
#   - SNMP port: 161xx (mapeado al contenedor)
# ═══════════════════════════════════════════════════════════════════════════════

API="http://localhost:8001/api/v1"
set -e

echo "═══ Orbis360 — Registrando red simulada ═══"
echo ""

# Login
echo "→ Iniciando sesión..."
TOKEN=$(curl -sf -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
echo "  ✓ Token obtenido"

# Limpiar datos anteriores de simulación
echo ""
echo "→ Limpiando datos de simulación anteriores..."
docker exec orbis360-db psql -U orbis360 -d orbis360_network -c "
DELETE FROM incidents WHERE device_id IN (SELECT id FROM devices WHERE hostname LIKE 'sim-%');
DELETE FROM metrics WHERE device_id IN (SELECT id FROM devices WHERE hostname LIKE 'sim-%');
DELETE FROM links WHERE source_device_id IN (SELECT id FROM devices WHERE hostname LIKE 'sim-%') OR target_device_id IN (SELECT id FROM devices WHERE hostname LIKE 'sim-%');
DELETE FROM devices WHERE hostname LIKE 'sim-%';
DELETE FROM locations WHERE name IN ('Cuarto de Telecomunicaciones','IDF Piso 2','Data Center');
" 2>/dev/null
echo "  ✓ Datos anteriores eliminados"

api_post() {
  curl -sf -X POST "$API/$1" -H "$AUTH" -H "Content-Type: application/json" -d "$2"
}

# Ubicaciones
echo ""
echo "→ Creando ubicaciones..."
LOC1=$(api_post "locations" '{"name":"Cuarto de Telecomunicaciones","building":"Torre Principal","floor":"1","area":"Networking"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ P1: $LOC1"
LOC2=$(api_post "locations" '{"name":"IDF Piso 2","building":"Torre Principal","floor":"2","area":"Oficinas"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ P2: $LOC2"
LOC3=$(api_post "locations" '{"name":"Data Center","building":"Torre Principal","floor":"3","area":"Servidores"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ P3: $LOC3"

# Dispositivos — todos en 127.0.0.1 con puertos SSH/SNMP diferentes
echo ""
echo "→ Creando dispositivos..."

FW=$(api_post "devices" "{
  \"hostname\":\"sim-firewall-01\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"firewall\",\"vendor\":\"Fortinet\",\"model\":\"FortiGate 100F\",
  \"is_critical\":true,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2210,
  \"snmp_community\":\"public\",\"snmp_port\":16110,\"location_id\":\"$LOC1\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-firewall-01 (SSH:2210, SNMP:16110)"

CR=$(api_post "devices" "{
  \"hostname\":\"sim-core-router-01\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"router\",\"vendor\":\"Cisco\",\"model\":\"ISR 4451\",
  \"is_critical\":true,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2211,
  \"snmp_community\":\"public\",\"snmp_port\":16111,\"location_id\":\"$LOC1\",\"parent_device_id\":\"$FW\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-core-router-01 (SSH:2211, SNMP:16111)"

CS=$(api_post "devices" "{
  \"hostname\":\"sim-core-switch-01\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"switch\",\"vendor\":\"Cisco\",\"model\":\"Catalyst 9300\",
  \"is_critical\":true,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2212,
  \"snmp_community\":\"public\",\"snmp_port\":16112,\"location_id\":\"$LOC1\",\"parent_device_id\":\"$CR\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-core-switch-01 (SSH:2212, SNMP:16112)"

DS2=$(api_post "devices" "{
  \"hostname\":\"sim-dist-switch-f2\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"switch\",\"vendor\":\"Cisco\",\"model\":\"Catalyst 3850\",
  \"is_critical\":false,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2220,
  \"snmp_community\":\"public\",\"snmp_port\":16120,\"location_id\":\"$LOC2\",\"parent_device_id\":\"$CS\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-dist-switch-f2 (SSH:2220, SNMP:16120)"

DS3=$(api_post "devices" "{
  \"hostname\":\"sim-dist-switch-f3\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"switch\",\"vendor\":\"Cisco\",\"model\":\"Catalyst 3850\",
  \"is_critical\":false,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2230,
  \"snmp_community\":\"public\",\"snmp_port\":16130,\"location_id\":\"$LOC3\",\"parent_device_id\":\"$CS\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-dist-switch-f3 (SSH:2230, SNMP:16130)"

AP2=$(api_post "devices" "{
  \"hostname\":\"sim-ap-f2-01\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"access_point\",\"vendor\":\"Ubiquiti\",\"model\":\"U6-Pro\",
  \"is_critical\":false,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2221,
  \"snmp_community\":\"public\",\"snmp_port\":16121,\"location_id\":\"$LOC2\",\"parent_device_id\":\"$DS2\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-ap-f2-01 (SSH:2221, SNMP:16121)"

AP3=$(api_post "devices" "{
  \"hostname\":\"sim-ap-f3-01\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"access_point\",\"vendor\":\"Ubiquiti\",\"model\":\"U6-LR\",
  \"is_critical\":false,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2231,
  \"snmp_community\":\"public\",\"snmp_port\":16131,\"location_id\":\"$LOC3\",\"parent_device_id\":\"$DS3\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-ap-f3-01 (SSH:2231, SNMP:16131)"

SRV=$(api_post "devices" "{
  \"hostname\":\"sim-server-dc-01\",\"ip_address\":\"127.0.0.1\",
  \"device_type\":\"server\",\"vendor\":\"Dell\",\"model\":\"PowerEdge R740\",
  \"is_critical\":true,\"ssh_username\":\"root\",\"ssh_password\":\"admin123\",\"ssh_port\":2200,
  \"snmp_community\":\"public\",\"snmp_port\":16100,\"location_id\":\"$LOC3\",\"parent_device_id\":\"$DS3\"
}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  ✓ sim-server-dc-01 (SSH:2200, SNMP:16100)"

# Enlaces
echo ""
echo "→ Creando enlaces..."
api_post "links" "{\"source_device_id\":\"$FW\",\"target_device_id\":\"$CR\",\"source_port\":\"port1\",\"target_port\":\"Gi0/0\",\"link_type\":\"fiber\",\"bandwidth_mbps\":10000}" > /dev/null
echo "  ✓ Firewall → Core Router (10G fibra)"
api_post "links" "{\"source_device_id\":\"$CR\",\"target_device_id\":\"$CS\",\"source_port\":\"Gi0/1\",\"target_port\":\"Te1/0/1\",\"link_type\":\"fiber\",\"bandwidth_mbps\":10000}" > /dev/null
echo "  ✓ Core Router → Core Switch (10G fibra)"
api_post "links" "{\"source_device_id\":\"$CS\",\"target_device_id\":\"$DS2\",\"source_port\":\"Te1/0/2\",\"target_port\":\"Te1/0/1\",\"link_type\":\"fiber\",\"bandwidth_mbps\":10000}" > /dev/null
echo "  ✓ Core Switch → Dist Switch P2 (10G fibra)"
api_post "links" "{\"source_device_id\":\"$CS\",\"target_device_id\":\"$DS3\",\"source_port\":\"Te1/0/3\",\"target_port\":\"Te1/0/1\",\"link_type\":\"fiber\",\"bandwidth_mbps\":10000}" > /dev/null
echo "  ✓ Core Switch → Dist Switch P3 (10G fibra)"
api_post "links" "{\"source_device_id\":\"$DS2\",\"target_device_id\":\"$AP2\",\"source_port\":\"Gi1/0/1\",\"target_port\":\"eth0\",\"link_type\":\"copper\",\"bandwidth_mbps\":1000}" > /dev/null
echo "  ✓ Dist Switch P2 → AP P2 (1G cobre)"
api_post "links" "{\"source_device_id\":\"$DS3\",\"target_device_id\":\"$AP3\",\"source_port\":\"Gi1/0/1\",\"target_port\":\"eth0\",\"link_type\":\"copper\",\"bandwidth_mbps\":1000}" > /dev/null
echo "  ✓ Dist Switch P3 → AP P3 (1G cobre)"
api_post "links" "{\"source_device_id\":\"$DS3\",\"target_device_id\":\"$SRV\",\"source_port\":\"Gi1/0/10\",\"target_port\":\"iDRAC\",\"link_type\":\"copper\",\"bandwidth_mbps\":1000}" > /dev/null
echo "  ✓ Dist Switch P3 → Server DC (1G cobre)"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✓ Red simulada registrada"
echo ""
echo "  8 dispositivos · 7 enlaces · 3 ubicaciones"
echo "  Todos los dispositivos responden a ping (127.0.0.x)"
echo "  SNMP y SSH en puertos mapeados en localhost"
echo ""
echo "  El monitor comenzará a detectarlos como UP en ~15s"
echo ""
echo "  Simular caídas:"
echo "    docker stop sim-core-switch-01   # caída en cascada"
echo "    docker stop sim-ap-f2-01         # fallo aislado"
echo "    docker start sim-core-switch-01  # restaurar"
echo "═══════════════════════════════════════════════════════════════"
