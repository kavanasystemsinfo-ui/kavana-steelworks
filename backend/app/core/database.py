"""Motor de base de datos: SQLAlchemy 2.0 + PostgreSQL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""
