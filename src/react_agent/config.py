# src/my_app/config.py
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


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

    DEBUG: bool = False

    JWT_SECRET_KEY: str 
    JWT_ALGORITHM: str = "HS256" 
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    SANDBOX_REPO_PATH: str
    
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
