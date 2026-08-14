"""Configuración de la aplicación KAVANA Steelworks."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno con defaults de desarrollo."""

    app_name: str = "KAVANA Steelworks API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://kavana:kavana@localhost:5432/kavana_steelworks"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8  # un turno estándar de fábrica (decisión legacy)

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="STEELWORKS_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
