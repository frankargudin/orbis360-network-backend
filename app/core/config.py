"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Orbis360 Network Monitor"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://orbis360:orbis360secret@localhost:5432/orbis360_network"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # JWT Auth
    JWT_SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # SNMP
    SNMP_COMMUNITY: str = "public"
    SNMP_TIMEOUT: int = 2
    SNMP_RETRIES: int = 1

    # Monitoring
    PING_INTERVAL_SECONDS: int = 30
    SNMP_POLL_INTERVAL_SECONDS: int = 60
    HEALTH_CHECK_INTERVAL_SECONDS: int = 10
    DOWN_THRESHOLD: int = 3  # consecutive failures before marking DOWN

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:4200", "https://orbis360-network-frontend.vercel.app"]

    model_config = {"env_file": ".env", "env_prefix": "ORBIS_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
