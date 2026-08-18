"""Fixtures de test: BD SQLite en memoria + sesión + datos base."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Tenant

TEST_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def db_session():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # BD en memoria COMPARTIDA entre conexiones (TestClient)
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
    t = Tenant(
        name="Aceros Test",
        slug="aceros-test",
        status="active",
        is_active=True,
        auth={},
        theme={},
        finances={},
        sequences_config={},
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture()
def user(db_session, tenant):
    from tests.helpers import make_user

    return make_user(db_session, tenant, email="operario@test.local", role="operator")
