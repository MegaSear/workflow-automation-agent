from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class MyDefaultSettings(BaseSettings):
    # Internal MCP service
    MY_DEFAULT_MCP_URL: str
    MY_DEFAULT_MCP_TOKEN: str

    # HTTP
    ALLOWED_HOSTS_FILE: Path = PROJECT_ROOT / "config" / "http_allowed_hosts.txt"
    ALLOWED_PORTS: set[int] = {443}
    REQUEST_TIMEOUT: int = 10
    MAX_BODY_BYTES: int = 100_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
    )


settings = MyDefaultSettings()
