from react_agent.config import Settings
import pytest
from pydantic import ValidationError

def test_database_url_uses_explicit_database_url():
    custom_url = "postgresql://user:password@localhost:5432/test_db"

    settings = Settings(
        LLM_API_KEY="test-key",
        LLM_BASE_URL="https://example.com/v1",
        LLM_MODEL="test-model",
        POSTGRES_DB="default_db",
        POSTGRES_USER="default_user",
        POSTGRES_PASSWORD="default_password",
        POSTGRES_PORT=5432,
        DATABASE_URL=custom_url,
        JWT_SECRET_KEY="test-secret-for-config-validation-1234567890",
    )

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
        Settings(
            LLM_API_KEY="test-key",
            LLM_BASE_URL="https://example.com/v1",
            LLM_MODEL="test-model",
            POSTGRES_DB="default_db",
            POSTGRES_USER="default_user",
            POSTGRES_PASSWORD="default_password",
            POSTGRES_PORT=5432,
            JWT_SECRET_KEY=secret,
        )


def test_jwt_secret_accepts_long_value():
    secret = "test-secret-for-config-validation-1234567890"

    settings = Settings(
        LLM_API_KEY="test-key",
        LLM_BASE_URL="https://example.com/v1",
        LLM_MODEL="test-model",
        POSTGRES_DB="default_db",
        POSTGRES_USER="default_user",
        POSTGRES_PASSWORD="default_password",
        POSTGRES_PORT=5432,
        JWT_SECRET_KEY=secret,
    )

    assert settings.JWT_SECRET_KEY == secret