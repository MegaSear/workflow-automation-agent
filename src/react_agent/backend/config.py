from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Provider
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_MAX_COMPLETION_TOKENS: int = Field(default=1024, ge=1)
    LLM_TEMPERATURE: float | None = Field(default=None, ge=0, le=2)
    LLM_TOP_P: float | None = Field(default=None, gt=0, le=1)
    LLM_FREQUENCY_PENALTY: float | None = Field(default=None, ge=-2, le=2)
    LLM_PRESENCE_PENALTY: float | None = Field(default=None, ge=-2, le=2)
    LLM_SEED: int | None = Field(default=None, ge=0)
    LLM_REASONING_EFFORT: Literal["low", "medium", "high"] | None = None
    LLM_PARALLEL_TOOL_CALLS: bool = True
    LLM_WARMUP_ENABLED: bool = False

    # FULLSTACK
    FRONTEND_URL: str | None

    # PostgreSQL
    DATABASE_MODE: str = "compose"
    DATABASE_URL: str | None = None
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_PORT: int
    POSTGRES_HOST: str = "localhost"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ENCRYPT CREDENTIALS
    INTEGRATION_ENCRYPTION_KEY: str | None

    # Google Calendar
    GOOGLE_CALENDAR_CREDENTIALS_FILE: Path = (
        PROJECT_ROOT / "secrets" / "google_web_credentials.json"
    )
    GOOGLE_CALENDAR_TOKEN_FILE: Path = PROJECT_ROOT / "secrets" / "google_token.json"
    GOOGLE_CALENDAR_REDIRECT_URI: str | None

    # JIRA MCP
    JIRA_MCP_URL: str | None

    # MCP service
    MY_DEFAULT_MCP_URL: str
    MY_DEFAULT_MCP_TOKEN: str | None

    # Internal MCP service
    GOOGLE_CALENDAR_MCP_URL: str | None
    GITHUB_MCP_URL: str | None

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_key(cls, value: str) -> str:
        """Reject short or obviously weak JWT signing secrets."""
        if len(value.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 bytes long. "
                "Generate a random value using Python secrets."
            )

        if any(character.isspace() for character in value):
            raise ValueError("JWT_SECRET_KEY must not contain whitespace")

        if len(set(value)) < 8:
            raise ValueError(
                "JWT_SECRET_KEY is too repetitive. "
                "Use a cryptographically random secret."
            )

        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
    )

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str | URL:
        if self.DATABASE_URL:
            return self.DATABASE_URL

        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )


settings = Settings()
