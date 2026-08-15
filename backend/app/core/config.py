"""Configuración de la aplicación KAVANA Steelworks."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalizar_database_url(url: str) -> str:
    """Acepta postgres:// (Fly/Render/Neon) y la pasa a postgresql+psycopg://."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url.split("://")[0]:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Settings(BaseSettings):
    """Variables de entorno con defaults de desarrollo."""

    app_name: str = "KAVANA Steelworks API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = Field(
        default="postgresql+psycopg://kavana:kavana@localhost:5432/kavana_steelworks",
        validation_alias=AliasChoices("STEELWORKS_DATABASE_URL", "DATABASE_URL"),
    )

    jwt_secret: str = Field(
        default="dev-secret-change-me",
        validation_alias=AliasChoices("STEELWORKS_JWT_SECRET", "JWT_SECRET"),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8  # un turno estándar de fábrica (decisión legacy)

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://steelworks.kavanasystems.com",
        "https://steelworks-kavana.vercel.app",
    ]

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="STEELWORKS_", extra="ignore"
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        return _normalizar_database_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
