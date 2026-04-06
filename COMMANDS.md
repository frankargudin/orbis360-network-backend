# Orbis360 Network Monitor — Comandos Útiles

## Requisitos previos

- Node.js 24+
- Python 3.14+
- Docker Desktop corriendo
- PostgreSQL (via Docker)

---

## 1. Levantar la plataforma completa

### Base de datos (PostgreSQL)
```bash
cd /Users/fargudin/Projects/workspace-angular/orbis360-network
docker compose up postgres -d
```

### Backend (FastAPI)
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

### Frontend (Angular)
```bash
cd frontend
npx ng serve --proxy-config proxy.conf.json --port 4200
```

### Todo en background (una sola línea)
```bash
cd /Users/fargudin/Projects/workspace-angular/orbis360-network

# DB
docker compose up postgres -d

# Backend
cd backend && source .venv/bin/activate && nohup uvicorn app.main:app --reload --port 8001 > /tmp/orbis360-backend.log 2>&1 &

# Frontend
cd ../frontend && nohup npx ng serve --proxy-config proxy.conf.json --port 4200 > /tmp/orbis360-frontend.log 2>&1 &
```

---

## 2. Acceso a la aplicación

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:4200 |
| Backend API | http://localhost:8001 |
| Swagger Docs | http://localhost:8001/docs |
| Login | `admin` / `admin123` |

---

## 3. Simulación de red

### Levantar los 8 dispositivos simulados
```bash
cd simulation
docker compose -f docker-compose.sim.yml up -d
```

### Registrar dispositivos en la plataforma
```bash
cd simulation
bash seed_simulated_network.sh
```

### Ver estado de los contenedores
```bash
cd simulation
bash simulate_failure.sh status
```

### Detener la simulación completa
```bash
cd simulation
docker compose -f docker-compose.sim.yml down
```

---

## 4. Simular caídas de red

### Tumbar un dispositivo específico
```bash
docker stop sim-core-router-01      # Core Router (cascada total)
docker stop sim-core-switch-01      # Core Switch (cascada parcial)
docker stop sim-dist-switch-f2      # Switch distribución piso 2
docker stop sim-dist-switch-f3      # Switch distribución piso 3
docker stop sim-ap-f2-01            # Access Point piso 2 (aislado)
docker stop sim-ap-f3-01            # Access Point piso 3 (aislado)
docker stop sim-firewall-01         # Firewall (gateway)
docker stop sim-server-dc-01        # Servidor DC (aislado)
```

### Levantar un dispositivo específico
```bash
docker start sim-core-router-01
docker start sim-core-switch-01
docker start sim-ap-f3-01
# etc.
```

### Verificar que arrancó
```bash
docker ps | grep sim-core-router
```

### Escenarios predefinidos
```bash
cd simulation

bash simulate_failure.sh core-switch    # Cascada desde core switch
bash simulate_failure.sh core-router    # Cascada total (todo menos firewall)
bash simulate_failure.sh ap             # Fallo aislado de un AP
bash simulate_failure.sh floor3         # Todo el piso 3 cae
bash simulate_failure.sh server         # Solo el servidor
bash simulate_failure.sh firewall       # Gateway caído
bash simulate_failure.sh random         # Dispositivo aleatorio
bash simulate_failure.sh restore        # Restaurar TODOS
bash simulate_failure.sh status         # Ver estado actual
```

---

## 5. Tiempos de detección

| Evento | Tiempo aproximado |
|--------|-------------------|
| Primer fallo (degradado/amarillo) | ~10 segundos |
| Confirmado DOWN (rojo) | ~30 segundos (3 fallos) |
| Cascada a hijos | Inmediata al confirmar DOWN |
| Recuperación (verde) | ~10 segundos después del `docker start` |
| Recuperación de hijos | Inmediata al recuperar padre |

---

## 6. Verificar estado via API

### Obtener token
```bash
TOKEN=$(curl -sf -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
```

### Resumen de dispositivos
```bash
curl -s http://localhost:8001/api/v1/devices/summary \
  -H "Authorization: Bearer $TOKEN"
```

### Listar todos los dispositivos
```bash
curl -s http://localhost:8001/api/v1/devices \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Ver incidentes abiertos
```bash
curl -s "http://localhost:8001/api/v1/incidents?status=open" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Ver topología (nodos y enlaces)
```bash
curl -s http://localhost:8001/api/v1/topology \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Ejecutar análisis de causa raíz
```bash
curl -s -X POST http://localhost:8001/api/v1/topology/rca \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 7. Gestión de dispositivos via API

### Crear dispositivo
```bash
curl -s -X POST http://localhost:8001/api/v1/devices \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "nuevo-switch-01",
    "ip_address": "192.168.1.50",
    "device_type": "switch",
    "vendor": "Cisco",
    "model": "Catalyst 3850",
    "snmp_community": "public",
    "snmp_port": 161,
    "ssh_username": "admin",
    "ssh_password": "password123",
    "ssh_port": 22,
    "is_critical": false
  }'
```

### Editar dispositivo
```bash
curl -s -X PATCH http://localhost:8001/api/v1/devices/{DEVICE_ID} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"vendor": "Juniper", "model": "EX3400"}'
```

### Eliminar dispositivo
```bash
curl -s -X DELETE http://localhost:8001/api/v1/devices/{DEVICE_ID} \
  -H "Authorization: Bearer $TOKEN"
```

### Reiniciar dispositivo via SSH
```bash
curl -s -X POST http://localhost:8001/api/v1/devices/{DEVICE_ID}/reboot \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

---

## 8. Base de datos

### Conectar a PostgreSQL
```bash
PGPASSWORD=orbis360secret psql -h localhost -p 5433 -U orbis360 -d orbis360_network
```

### Queries útiles
```sql
-- Dispositivos caídos
SELECT hostname, ip_address, consecutive_failures FROM devices WHERE status = 'down';

-- Incidentes abiertos
SELECT title, severity, detected_at FROM incidents WHERE status = 'open' ORDER BY detected_at DESC;

-- Latencia promedio por dispositivo (últimas 24h)
SELECT d.hostname, AVG(m.latency_ms) as avg_latency
FROM metrics m JOIN devices d ON m.device_id = d.id
WHERE m.timestamp > NOW() - INTERVAL '24 hours'
GROUP BY d.hostname ORDER BY avg_latency DESC;

-- Dispositivos que más fallan
SELECT d.hostname, COUNT(i.id) as total_incidentes
FROM incidents i JOIN devices d ON i.device_id = d.id
GROUP BY d.hostname ORDER BY total_incidentes DESC LIMIT 10;

-- Dispositivos por edificio/piso
SELECT l.building, l.floor, COUNT(d.id) as total
FROM devices d JOIN locations l ON d.location_id = l.id
GROUP BY l.building, l.floor ORDER BY l.building, l.floor;
```

### Limpiar datos de simulación
```bash
docker exec orbis360-db psql -U orbis360 -d orbis360_network -c "
DELETE FROM incidents;
DELETE FROM metrics;
DELETE FROM links WHERE source_device_id IN (SELECT id FROM devices WHERE hostname LIKE 'sim-%');
DELETE FROM devices WHERE hostname LIKE 'sim-%';
DELETE FROM locations WHERE building = 'Torre Principal';
"
```

### Resetear toda la base de datos
```bash
docker compose down -v   # Elimina el volumen de datos
docker compose up postgres -d   # Recrea desde init.sql
```

---

## 9. Logs

### Ver logs del backend
```bash
tail -f /tmp/orbis360-backend.log
```

### Ver logs del frontend
```bash
tail -f /tmp/orbis360-frontend.log
```

### Ver logs de un contenedor simulado
```bash
docker logs -f sim-core-router-01
```

---

## 10. Detener todo

### Detener servicios
```bash
pkill -f "uvicorn app.main"    # Backend
pkill -f "ng serve"            # Frontend
```

### Detener simulación
```bash
cd simulation
docker compose -f docker-compose.sim.yml down
```

### Detener PostgreSQL
```bash
docker compose down
```

### Nuclear (detener todo + borrar datos)
```bash
cd simulation && docker compose -f docker-compose.sim.yml down
cd .. && docker compose down -v
pkill -f "uvicorn app.main"
pkill -f "ng serve"
```

---

## 11. Topología de la red simulada

```
  [sim-firewall-01]        ← Firewall (gateway)
        │
  [sim-core-router-01]     ← Core Router (crítico)
        │
  [sim-core-switch-01]     ← Core Switch (crítico)
      ┌───┴───┐
[sim-dist-f2] [sim-dist-f3]  ← Distribution Switches
    │             ├───────┐
[sim-ap-f2]  [sim-ap-f3] [sim-server-dc]
```

### Credenciales de los dispositivos simulados
- **SSH**: `root` / `admin123`
- **SNMP**: community `public`
- **Puertos SSH**: 2200-2231 (mapeados en localhost)
- **Puertos SNMP**: 16100-16131 (mapeados en localhost)

---

## 12. Compilar para producción

### Frontend
```bash
cd frontend
npx ng build --configuration=production
# Output en: dist/frontend/browser/
```

### Backend
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Compose completo (producción)
```bash
docker compose up -d  # Levanta postgres + backend + frontend
```
