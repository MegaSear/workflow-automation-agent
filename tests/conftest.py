import os
import tempfile

os.environ.update(
    {
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.invalid/v1",
        "LLM_MODEL": "test-model",
        "FRONTEND_URL": "http://localhost:3000",
        "DATABASE_URL": "sqlite://",
        "POSTGRES_DB": "test",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_PORT": "5432",
        "JWT_SECRET_KEY": "test-secret-key-for-tests-only-0123456789",
        "GOOGLE_CALENDAR_REDIRECT_URI": "http://localhost:8000/oauth/callback",
        "INTEGRATION_ENCRYPTION_KEY": "test-encryption-key",
        "JIRA_MCP_URL": "http://localhost:8004/mcp",
        "MY_DEFAULT_MCP_URL": "http://my-default:8001/mcp",
        "MY_DEFAULT_MCP_TOKEN": "test-internal-mcp-token",
        "GOOGLE_CALENDAR_MCP_URL": "http://localhost:8002/mcp",
        "GITHUB_MCP_URL": "http://localhost:8003/mcp",
    }
)


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def load_test_application():
    original_directory = os.getcwd()
    with tempfile.TemporaryDirectory() as isolated_directory:
        os.chdir(isolated_directory)
        try:
            from react_agent.backend.api import server
            from react_agent.backend.api.server import app
            from react_agent.backend.auth.auth import get_current_user
            from react_agent.backend.db.database import Base, get_db
            from react_agent.backend.db.models import User
        finally:
            os.chdir(original_directory)

    return app, get_current_user, Base, get_db, User, server


app, get_current_user, Base, get_db, User, server = load_test_application()

_ORIGINAL_DIRECTORY = os.getcwd()
_ISOLATED_SETTINGS_DIRECTORY = tempfile.TemporaryDirectory()


def pytest_sessionstart(session):
    os.chdir(_ISOLATED_SETTINGS_DIRECTORY.name)


def pytest_sessionfinish(session, exitstatus):
    os.chdir(_ORIGINAL_DIRECTORY)
    _ISOLATED_SETTINGS_DIRECTORY.cleanup()


@pytest.fixture(scope="session", autouse=True)
def disable_llm_warmup():
    original_warmup = server.llm_client.warmup
    server.llm_client.warmup = lambda context: "test warmup"
    yield
    server.llm_client.warmup = original_warmup


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
