import os

os.environ.update(
    {
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.invalid/v1",
        "LLM_MODEL": "test-model",
        "DATABASE_URL": "sqlite://",
        "POSTGRES_DB": "test",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_PORT": "5432",
        "JWT_SECRET_KEY": "test-secret-key-for-tests-only-0123456789",
    }
)


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from react_agent.api.server import app
from react_agent.auth.auth import get_current_user
from react_agent.db.database import Base, get_db
from react_agent.db.models import User


@pytest.fixture
def db_engine():
    """Create an isolated in-memory SQLite database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a database session for a single test."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_engine):
    """Provide a test client connected to the test database."""

    def override_get_db():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    """Create a user for API tests."""
    user = User(
        email="test@example.com",
        password_hash="unused",
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


@pytest.fixture
def authenticated_client(client, test_user):
    """Provide a client authenticated as test_user."""
    app.dependency_overrides[get_current_user] = lambda: test_user

    yield client

    app.dependency_overrides.pop(get_current_user, None)
