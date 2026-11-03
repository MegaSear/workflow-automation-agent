import base64
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from sqlalchemy.orm import Session

from react_agent.backend.config import PROJECT_ROOT, settings
from react_agent.backend.integrations.credentials import get_credentials
from react_agent.backend.integrations.google_oauth import (
    get_google_calendar_access_token,
)
from react_agent.backend.mcp.manager import connect_remote_mcp

logger = logging.getLogger(__name__)
MCP_CONFIG_PATH = (
    PROJECT_ROOT / "src" / "react_agent" / "backend" / "mcp" / "mcp_config.yaml"
)
ENVIRONMENT_VARIABLE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def load_mcp_server_specs(path: Path = MCP_CONFIG_PATH) -> dict[str, dict]:
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError("MCP server configuration cannot be loaded") from error

    servers = config.get("servers")
    if not isinstance(servers, dict):
        raise RuntimeError("MCP configuration must define a servers mapping")
    return {
        name: spec
        for name, spec in servers.items()
        if isinstance(spec, dict) and spec.get("enabled", True)
    }


def _expand_environment(value: str) -> str | None:
    missing = False

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        variable, default = match.groups()
        result = os.environ.get(variable)
        if result is None:
            result = getattr(settings, variable, default)
        if result is None:
            missing = True
            return ""
        return result

    expanded = ENVIRONMENT_VARIABLE.sub(replace, value)
    return None if missing else expanded.strip()


def _credential_headers(
    provider: str,
    *,
    db: Session,
    user_id: int,
) -> dict[str, str] | None:
    credentials = get_credentials(db, user_id=user_id, provider=provider)
    if not credentials:
        logger.info(
            "MCP server %s skipped: user has no connected credentials", provider
        )
        return None

    if provider == "github":
        token = credentials.get("token") or credentials.get("access_token")
        if not isinstance(token, str) or not token.strip():
            return None
        return {"Authorization": f"Bearer {token}"}

    if provider == "jira":
        email = credentials.get("email")
        token = credentials.get("api_token")
        if not isinstance(email, str) or not isinstance(token, str):
            return None
        encoded = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    if provider == "google_calendar":
        token = get_google_calendar_access_token(db, user_id=user_id)
        return {"Authorization": f"Bearer {token}"}

    logger.warning("Unknown MCP credential provider configured: %s", provider)
    return None


def create_mcp_client_factories(
    specs: dict[str, dict],
    *,
    db: Session,
    workspace_id: int,
    user_id: int,
) -> dict[str, Callable]:
    clients = {}
    for server_name, spec in specs.items():
        transport = spec.get("transport")
        provider = spec.get("credentials")

        if transport != "streamable_http":
            continue

        raw_url = spec.get("url")
        url = _expand_environment(raw_url) if isinstance(raw_url, str) else None
        if not url:
            logger.warning(
                "MCP server %s skipped: endpoint URL is not configured", server_name
            )
            continue

        parsed = urlsplit(url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "my-default"}
        ):
            logger.warning(
                "MCP server %s skipped: endpoint must use HTTPS", server_name
            )
            continue

        if spec.get("auth") == "backend":
            token = settings.MY_DEFAULT_MCP_TOKEN
            if not token:
                logger.warning(
                    "MCP server %s skipped: backend MCP authentication is not configured",
                    server_name,
                )
                continue
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Workspace-ID": str(workspace_id),
            }
        else:
            headers = (
                _credential_headers(
                    provider,
                    db=db,
                    user_id=user_id,
                )
                if isinstance(provider, str)
                else {}
            )
        if headers is None:
            continue

        clients[server_name] = lambda endpoint=url, auth_headers=headers: (
            connect_remote_mcp(
                endpoint,
                headers=auth_headers,
            )
        )

    return clients
