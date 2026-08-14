"""Fixtures de test: BD SQLite en memoria + sesión + datos base."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Tenant, User

TEST_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def db_session():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def tenant(db_session):
    t = Tenant(name="Aceros Test")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture()
def user(db_session, tenant):
    u = User(
        tenant_id=tenant.id,
        email="operario@test.local",
        name="Operario Test",
        password_hash="x",
        role="operator",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u
