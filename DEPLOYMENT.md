# Orbis360 — Guía de Despliegue en Producción

## Arquitectura

```
                    Internet
                       │
         ┌─────────────┴─────────────┐
         │                           │
    ┌────┴────┐               ┌──────┴──────┐
    │  Vercel │   /api/* →    │   Railway   │
    │ Angular │──────────────→│   FastAPI   │
    │  (SPA)  │   rewrite     │  (backend)  │
    └─────────┘               │      │      │
                              │  ┌───┴───┐  │
                              │  │ PostgreSQL│
                              │  │ (addon)   │
                              │  └───────┘  │
                              └─────────────┘
```

- **Vercel**: sirve el frontend Angular como sitio estático. Las peticiones a `/api/*` se redirigen a Railway.
- **Railway**: ejecuta el backend FastAPI + PostgreSQL como addon.

---

## Paso 1: Subir el código a GitHub

```bash
cd /Users/fargudin/Projects/workspace-angular/orbis360-network

git init
git add .
git commit -m "Orbis360 Network Monitor — initial commit"
git remote add origin https://github.com/TU_USUARIO/orbis360-network.git
git push -u origin main
```

---

## Paso 2: Railway — PostgreSQL

1. Ir a [railway.app](https://railway.app) → **New Project**
2. Click **"Provision PostgreSQL"** (o agregar addon después)
3. Una vez creada, ir a la pestaña **Variables** del servicio PostgreSQL
4. Copiar la variable `DATABASE_URL`. Se ve algo así:
   ```
   postgresql://postgres:XXXXXX@containers-us-west-XXX.railway.app:5432/railway
   ```
5. **Importante**: para nuestro backend necesitas agregar `+asyncpg` al driver:
   ```
   postgresql+asyncpg://postgres:XXXXXX@containers-us-west-XXX.railway.app:5432/railway
   ```

---

## Paso 3: Railway — Backend

1. En el mismo proyecto Railway, click **"New Service"** → **"GitHub Repo"**
2. Seleccionar tu repo `orbis360-network`
3. Configurar:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile (se detecta automáticamente)

4. Ir a la pestaña **Variables** y agregar:

   | Variable | Valor |
   |----------|-------|
   | `ORBIS_DATABASE_URL` | `postgresql+asyncpg://postgres:XXXXX@host:5432/railway` (la del paso 2 con `+asyncpg`) |
   | `ORBIS_JWT_SECRET_KEY` | Generar con: `openssl rand -hex 32` |
   | `ORBIS_DEBUG` | `false` |
   | `ORBIS_CORS_ORIGINS` | `["https://orbis360-TU-PROYECTO.vercel.app"]` (se actualiza en paso 6) |
   | `ORBIS_SNMP_COMMUNITY` | `public` |
   | `ORBIS_HEALTH_CHECK_INTERVAL_SECONDS` | `30` |
   | `ORBIS_DOWN_THRESHOLD` | `3` |

5. Click **Deploy** — Railway construye la imagen Docker y la ejecuta
6. Una vez desplegado, ir a **Settings** → **Networking** → **Generate Domain**
7. Anotar la URL generada, ejemplo: `orbis360-api-production.up.railway.app`
8. Verificar: abrir `https://TU-URL.railway.app/api/health` — debe responder `{"status":"healthy"}`

---

## Paso 4: Inicializar la base de datos

La primera vez que el backend arranca, crea las tablas automáticamente. Pero necesitas crear el usuario admin.

### Opción A: Via la API (recomendado)
```bash
# Registrar el admin
curl -X POST https://TU-URL.railway.app/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@tuempresa.com",
    "password": "TU_PASSWORD_SEGURO",
    "full_name": "Administrador",
    "role": "admin"
  }'
```

### Opción B: Via Railway CLI
```bash
# Instalar Railway CLI
npm install -g @railway/cli
railway login
railway link  # seleccionar tu proyecto

# Ejecutar el script SQL
railway run psql < database/init.sql
```

---

## Paso 5: Vercel — Frontend

1. Ir a [vercel.com](https://vercel.com) → **Add New Project**
2. Importar el repo `orbis360-network` de GitHub
3. Configurar:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Angular (Vercel lo detecta)
   - **Build Command**: `npx ng build --configuration=production`
   - **Output Directory**: `dist/frontend/browser`

4. Agregar **Environment Variable**:

   | Variable | Valor |
   |----------|-------|
   | `RAILWAY_BACKEND_URL` | `https://orbis360-api-production.up.railway.app` (la URL del paso 3) |

5. Click **Deploy**

6. Anotar la URL de Vercel, ejemplo: `orbis360-tu-proyecto.vercel.app`

---

## Paso 6: Actualizar CORS en Railway

Ahora que tienes la URL de Vercel, vuelve a Railway y actualiza la variable:

```
ORBIS_CORS_ORIGINS = ["https://orbis360-tu-proyecto.vercel.app"]
```

Railway re-desplegará automáticamente.

---

## Paso 7: Configurar WebSocket (si se necesita)

Si quieres que el WebSocket funcione en producción (actualizaciones en tiempo real):

1. Editar `frontend/src/environments/environment.prod.ts`:
   ```typescript
   export const environment = {
     production: true,
     wsUrl: 'https://orbis360-api-production.up.railway.app',
   };
   ```

2. Hacer commit y push — Vercel re-despliega automáticamente

> **Nota**: Sin WebSocket la app funciona igual, solo que las actualizaciones vienen por polling cada 10 segundos en vez de ser instantáneas.

---

## Paso 8: Verificación

1. Abrir `https://orbis360-tu-proyecto.vercel.app`
2. Hacer login con las credenciales del paso 4
3. Ir a **Dispositivos** → **Agregar Dispositivo** → agregar un equipo real de tu red
4. Esperar 30 segundos → el monitor debe detectarlo como UP (verde)

---

## Variables de entorno — Resumen

### Railway (Backend)
| Variable | Ejemplo | Obligatoria |
|----------|---------|-------------|
| `ORBIS_DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` | Sí |
| `ORBIS_JWT_SECRET_KEY` | `a1b2c3d4...` (64 chars hex) | Sí |
| `ORBIS_CORS_ORIGINS` | `["https://tu-app.vercel.app"]` | Sí |
| `ORBIS_DEBUG` | `false` | Sí |
| `ORBIS_SNMP_COMMUNITY` | `public` | No (default: public) |
| `ORBIS_HEALTH_CHECK_INTERVAL_SECONDS` | `30` | No (default: 10) |
| `ORBIS_DOWN_THRESHOLD` | `3` | No (default: 3) |
| `ORBIS_SNMP_TIMEOUT` | `3` | No (default: 2) |
| `ORBIS_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | No (default: 480) |

### Vercel (Frontend)
| Variable | Ejemplo | Obligatoria |
|----------|---------|-------------|
| `RAILWAY_BACKEND_URL` | `https://orbis360-api-xxx.railway.app` | Sí |

---

## Dominio personalizado (opcional)

### Vercel
1. **Settings** → **Domains** → agregar `monitor.tuempresa.com`
2. Configurar DNS: CNAME `monitor` → `cname.vercel-dns.com`

### Railway
1. **Settings** → **Networking** → **Custom Domain** → agregar `api.tuempresa.com`
2. Configurar DNS: CNAME `api` → Railway domain

Actualizar `ORBIS_CORS_ORIGINS` para incluir el nuevo dominio.

---

## Costos estimados

| Servicio | Plan | Costo |
|----------|------|-------|
| Vercel | Hobby (gratis) | $0/mes |
| Railway | Starter | ~$5/mes (backend + DB) |
| **Total** | | **~$5/mes** |

Para más de 500 dispositivos o alta disponibilidad, Railway Pro (~$20/mes) con más recursos.

---

## Troubleshooting

### "Not authenticated" en todas las páginas
- El token JWT expiró. Haz logout y login de nuevo.

### La API no responde desde Vercel
- Verificar que `RAILWAY_BACKEND_URL` está configurado en Vercel
- Verificar que `ORBIS_CORS_ORIGINS` incluye la URL de Vercel
- Revisar logs en Railway dashboard

### Los dispositivos no se detectan
- Verificar que la IP del dispositivo es accesible desde Railway (IP pública o VPN)
- SNMP community correcta
- Puerto 161 abierto en el firewall del dispositivo

### WebSocket no conecta
- Verificar `wsUrl` en `environment.prod.ts`
- Railway soporta WebSocket en su plan Starter

### Base de datos vacía
- Ejecutar el init.sql o crear el admin via API (paso 4)
