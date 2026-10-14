from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str

    DATABASE_MODE: str = "compose"
    DATABASE_URL: str | None = None

    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_PORT: int
    POSTGRES_HOST: str = "localhost"

    JWT_SECRET_KEY: str 
    JWT_ALGORITHM: str = "HS256" 
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    
    ALLOWED_HOSTS_FILE: Path = PROJECT_ROOT / "config" / "http_allowed_hosts.txt"

    ALLOWED_PORTS: set[int] = {443}
    REQUEST_TIMEOUT: int = 10
    MAX_BODY_BYTES: int = 100_000

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
            raise ValueError(
                "JWT_SECRET_KEY must not contain whitespace"
            )

        if len(set(value)) < 8:
            raise ValueError(
                "JWT_SECRET_KEY is too repetitive. "
                "Use a cryptographically random secret."
            )

        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str | URL:
        if self.DATABASE_URL:
            return self.DATABASE_URL

        return URL.create(
            drivername="postgresql",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )


settings = Settings()
