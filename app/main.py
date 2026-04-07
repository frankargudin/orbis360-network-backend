"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import auth, devices, incidents, links, locations, maintenance, metrics, thresholds, topology, websocket
from app.core.config import get_settings
from app.domain.models.base import Base
from app.infrastructure.database.session import engine
from app.workers.monitor import NetworkMonitorWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()
monitor_worker = NetworkMonitorWorker()


async def init_db():
    """Auto-create tables if they don't exist (for Railway/production first deploy)."""
    # Import all models so they register with Base.metadata
    from app.domain.models import network  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init DB, start background monitor on startup, stop on shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    monitor_task = asyncio.create_task(monitor_worker.start())
    yield
    await monitor_worker.stop()
    monitor_task.cancel()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(devices.router, prefix=API_PREFIX)
app.include_router(links.router, prefix=API_PREFIX)
app.include_router(locations.router, prefix=API_PREFIX)
app.include_router(incidents.router, prefix=API_PREFIX)
app.include_router(metrics.router, prefix=API_PREFIX)
app.include_router(maintenance.router, prefix=API_PREFIX)
app.include_router(thresholds.router, prefix=API_PREFIX)
app.include_router(topology.router, prefix=API_PREFIX)
app.include_router(websocket.router, prefix=API_PREFIX)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}
