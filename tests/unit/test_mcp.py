import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from starlette.testclient import TestClient

from react_agent.backend.config import settings
from react_agent.backend.integrations.credentials import save_credentials
from react_agent.backend.integrations.google_oauth import GOOGLE_CALENDAR_SCOPES
from react_agent.backend.integrations.jira import validate_jira_credentials
from react_agent.backend.mcp.manager import MCPManager
from react_agent.backend.mcp.registry import (
    create_mcp_client_factories,
    load_mcp_server_specs,
)
from react_agent.my_default.server import (
    create_my_default_app,
    create_my_default_server,
)


def test_manager_namespaces_and_dispatches_local_tools():
    server = MCPServer(name="sample")

    @server.tool()
    def add(left: int, right: int) -> str:
        return str(left + right)

    async def run():
        async with MCPManager(servers={"sample": server}) as manager:
            tools = manager.get_openai_tools()
            assert [tool["function"]["name"] for tool in tools] == ["sample__add"]
            return await manager.call_tool("sample__add", {"left": 2, "right": 3})

    assert asyncio.run(run()) == "5"


def test_my_default_mcp_server_exposes_only_its_owned_tools():
    async def run():
        async with MCPManager(
            servers={"my_default": create_my_default_server()},
        ) as manager:
            return {tool["function"]["name"] for tool in manager.get_openai_tools()}

    assert asyncio.run(run()) == {
        "my_default__create_file",
        "my_default__get_current_time",
        "my_default__git_status",
        "my_default__http_get",
        "my_default__read_file",
    }


def test_manager_exposes_unannotated_remote_write_tools():
    server = MCPServer(name="github")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def create_issue(title: str) -> str:
        return title

    @asynccontextmanager
    async def remote_client():
        async with Client(server, raise_exceptions=True) as client:
            yield client

    async def run():
        async with MCPManager(
            servers={},
            remote_clients={"github": remote_client},
        ) as manager:
            return manager.get_openai_tools()

    tools = asyncio.run(run())
    assert [tool["function"]["name"] for tool in tools] == ["github__create_issue"]


def test_manager_filters_tools_using_server_allowlist():
    server = MCPServer(name="github")

    @server.tool()
    def search_code(query: str) -> str:
        return query

    @server.tool()
    def create_issue(title: str) -> str:
        return title

    async def run():
        async with MCPManager(
            servers={"github": server},
            tool_allowlists={"github": {"search_code"}},
        ) as manager:
            return manager.get_openai_tools()

    tools = asyncio.run(run())
    assert [tool["function"]["name"] for tool in tools] == ["github__search_code"]


def test_enabled_mcp_servers_are_url_backed():
    specs = load_mcp_server_specs()

    assert set(specs) == {"my_default", "jira", "google_calendar", "github"}
    assert {spec["transport"] for spec in specs.values()} == {"streamable_http"}
    assert specs["my_default"]["auth"] == "backend"
    assert specs["github"]["tool_allowlist"] == [
        "get_file_contents",
        "search_code",
        "pull_request_read",
        "create_pull_request",
    ]


def test_my_default_remote_client_sends_workspace_and_service_auth(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "MY_DEFAULT_MCP_TOKEN", "internal-token")
    captured = {}

    @asynccontextmanager
    async def fake_connect_remote(url, headers):
        captured.update(url=url, headers=headers)
        yield "client"

    monkeypatch.setattr(
        "react_agent.backend.mcp.registry.connect_remote_mcp",
        fake_connect_remote,
    )
    clients = create_mcp_client_factories(
        {
            "my_default": {
                "transport": "streamable_http",
                "url": "http://my-default:8001/mcp",
                "auth": "backend",
            }
        },
        db=db_session,
        workspace_id=47,
        user_id=12,
    )

    async def run():
        async with clients["my_default"]() as client:
            return client

    assert asyncio.run(run()) == "client"
    assert captured == {
        "url": "http://my-default:8001/mcp",
        "headers": {
            "Authorization": "Bearer internal-token",
            "X-Workspace-ID": "47",
        },
    }


def test_my_default_mcp_rejects_requests_without_internal_auth():
    app = create_my_default_app(token="internal-token")

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={"X-Workspace-ID": "47"},
            content="{}",
        )

    assert response.status_code == 401


def test_integrations_are_remote_and_receive_user_credentials(
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    save_credentials(
        db_session,
        user_id=test_user.id,
        provider="jira",
        credentials={
            "base_url": "https://example.atlassian.net",
            "email": "test@example.com",
            "api_token": "jira-test-token",
        },
    )
    save_credentials(
        db_session,
        user_id=test_user.id,
        provider="google_calendar",
        credentials={
            "token": "google-test-token",
            "refresh_token": "google-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client",
            "client_secret": "test-secret",
            "scopes": GOOGLE_CALENDAR_SCOPES,
            "expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    monkeypatch.setenv("JIRA_MCP_URL", "https://jira.example/mcp")
    monkeypatch.setenv("GOOGLE_CALENDAR_MCP_URL", "https://calendar.example/mcp")
    captured = {}

    @asynccontextmanager
    async def fake_connect_remote(url, headers):
        captured[url] = headers
        yield "client"

    monkeypatch.setattr(
        "react_agent.backend.mcp.registry.connect_remote_mcp",
        fake_connect_remote,
    )
    clients = create_mcp_client_factories(
        load_mcp_server_specs(),
        db=db_session,
        workspace_id=test_user.id,
        user_id=test_user.id,
    )

    async def run():
        for client_factory in clients.values():
            async with client_factory():
                pass

    asyncio.run(run())
    assert set(clients) == {"my_default", "jira", "google_calendar"}
    assert set(captured) == {
        "http://my-default:8001/mcp",
        "https://jira.example/mcp",
        "https://calendar.example/mcp",
    }
    assert captured["https://jira.example/mcp"]["Authorization"].startswith("Basic ")
    assert captured["https://calendar.example/mcp"]["Authorization"] == (
        "Bearer google-test-token"
    )


def test_github_mcp_receives_connected_users_token(
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    save_credentials(
        db_session,
        user_id=test_user.id,
        provider="github",
        credentials={"token": "github-test-token"},
    )
    monkeypatch.setenv("GITHUB_MCP_URL", "https://github.example/mcp")
    captured = {}

    @asynccontextmanager
    async def fake_connect_remote(url, headers):
        captured.update(url=url, headers=headers)
        yield "client"

    monkeypatch.setattr(
        "react_agent.backend.mcp.registry.connect_remote_mcp",
        fake_connect_remote,
    )
    clients = create_mcp_client_factories(
        {
            "github": {
                "transport": "streamable_http",
                "url": "${GITHUB_MCP_URL}",
                "credentials": "github",
            }
        },
        db=db_session,
        workspace_id=test_user.id,
        user_id=test_user.id,
    )

    async def run():
        async with clients["github"]() as client:
            return client

    assert asyncio.run(run()) == "client"
    assert captured["url"] == "https://github.example/mcp"
    assert captured["headers"]["Authorization"] == "Bearer github-test-token"


def test_mcp_registry_skips_missing_remote_url(db_session, test_user, monkeypatch):
    monkeypatch.delenv("JIRA_MCP_URL", raising=False)
    clients = create_mcp_client_factories(
        {
            "jira": {
                "transport": "streamable_http",
                "url": "${JIRA_MCP_URL}",
                "credentials": "jira",
            }
        },
        db=db_session,
        workspace_id=test_user.id,
        user_id=test_user.id,
    )

    assert clients == {}


@pytest.mark.parametrize(
    ("credentials", "message"),
    [
        ({"api_token": "token"}, "Jira email is required"),
        ({"email": "test@example.com"}, "Jira API token is required"),
    ],
)
def test_jira_requires_credentials(credentials, message):
    with pytest.raises(ValueError, match=message):
        asyncio.run(validate_jira_credentials(credentials))


def test_jira_requires_configured_mcp_url(monkeypatch):
    monkeypatch.delenv("JIRA_MCP_URL", raising=False)

    with pytest.raises(ValueError, match="JIRA_MCP_URL is not configured"):
        asyncio.run(
            validate_jira_credentials(
                {"email": "test@example.com", "api_token": "token"}
            )
        )
