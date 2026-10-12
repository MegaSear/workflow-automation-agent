from react_agent.config import Settings


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
        JWT_SECRET_KEY="test-secret",
    )

    assert settings.SQLALCHEMY_DATABASE_URL == custom_url