import pytest
from pydantic import ValidationError

from react_agent.backend.config import Settings


def build_settings(**overrides):
    values = {
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_MODEL": "test-model",
        "FRONTEND_URL": "http://localhost:3000",
        "POSTGRES_DB": "default_db",
        "POSTGRES_USER": "default_user",
        "POSTGRES_PASSWORD": "default_password",
        "POSTGRES_PORT": 5432,
        "JWT_SECRET_KEY": "test-secret-for-config-validation-1234567890",
        "GOOGLE_CALENDAR_REDIRECT_URI": "http://localhost:8000/oauth/callback",
        "INTEGRATION_ENCRYPTION_KEY": "test-encryption-key",
        "JIRA_MCP_URL": "http://localhost:8004/mcp",
        "MY_DEFAULT_MCP_URL": "http://localhost:8001/mcp",
        "MY_DEFAULT_MCP_TOKEN": "test-token",
        "GOOGLE_CALENDAR_MCP_URL": "http://localhost:8002/mcp",
        "GITHUB_MCP_URL": "http://localhost:8003/mcp",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_uses_explicit_database_url():
    custom_url = "postgresql://user:password@localhost:5432/test_db"

    settings = build_settings(DATABASE_URL=custom_url)

    assert settings.SQLALCHEMY_DATABASE_URL == custom_url


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "short",
        "a" * 40,
        "this secret is long but has spaces",
    ],
)
def test_jwt_secret_rejects_weak_values(secret: str):
    with pytest.raises(ValidationError):
        build_settings(JWT_SECRET_KEY=secret)


def test_jwt_secret_accepts_long_value():
    secret = "test-secret-for-config-validation-1234567890"

    settings = build_settings(JWT_SECRET_KEY=secret)

    assert settings.JWT_SECRET_KEY == secret
