import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Callable

import httpx2
from mcp import Client
from mcp.types import TextContent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def connect_remote_mcp(
    url: str,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[Client]:
    async with httpx2.AsyncClient(
        headers=headers or {},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        from mcp.client.streamable_http import streamable_http_client

        transport = streamable_http_client(
            url,
            http_client=http_client,
        )
        async with Client(transport, raise_exceptions=True) as client:
            yield client


class MCPManager:
    def __init__(
        self,
        servers: dict[str, Any],
        remote_clients: dict[str, Callable[[], Any]] | None = None,
        tool_allowlists: dict[str, set[str]] | None = None,
    ):
        self._servers = servers
        self._remote_clients = remote_clients or {}
        self._tool_allowlists = tool_allowlists or {}

        self._stack: AsyncExitStack | None = None

        self._clients: dict[str, Client] = {}
        self._tool_routes: dict[str, tuple[Client, str]] = {}
        self._openai_tools: list[dict] = []

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        try:
            # Локальные MCP-серверы.
            for server_name, server in self._servers.items():
                client = await self._stack.enter_async_context(
                    Client(server, raise_exceptions=True)
                )

                await self._register_client(server_name, client)

            # Внешние MCP-клиенты.
            for server_name, client_factory in self._remote_clients.items():
                try:
                    client = await self._stack.enter_async_context(client_factory())
                    await self._register_client(
                        server_name,
                        client,
                    )
                except Exception as error:
                    logger.exception(
                        "Optional MCP server %s could not be connected: %s",
                        server_name,
                        self._safe_error_summary(error),
                    )

        except Exception:
            await self._stack.aclose()
            self._stack = None
            raise

        return self

    async def _register_client(
        self,
        server_name: str,
        client: Client,
    ) -> None:
        if server_name in self._clients:
            raise ValueError(f"Duplicate MCP server name: {server_name}")

        self._clients[server_name] = client

        cursor = None
        discovered_names = []

        while True:
            result = await client.list_tools(cursor=cursor)

            for tool in result.tools:
                allowed_tools = self._tool_allowlists.get(server_name)
                if allowed_tools is not None and tool.name not in allowed_tools:
                    continue

                exposed_name = f"{server_name}__{tool.name}"

                if exposed_name in self._tool_routes:
                    raise ValueError(f"Duplicate MCP tool name: {exposed_name}")

                self._tool_routes[exposed_name] = (
                    client,
                    tool.name,
                )
                discovered_names.append(exposed_name)

                self._openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": exposed_name,
                            "description": tool.description or "",
                            "parameters": tool.input_schema,
                        },
                    }
                )

            cursor = result.next_cursor

            if cursor is None:
                break

        logger.info(
            "MCP server %s exposed %d tools: %s",
            server_name,
            len(discovered_names),
            ", ".join(discovered_names),
        )

    @classmethod
    def _safe_error_summary(cls, error: BaseException) -> str:
        if isinstance(error, BaseExceptionGroup):
            return "; ".join(
                cls._safe_error_summary(child) for child in error.exceptions
            )
        response = getattr(error, "response", None)
        if response is not None and getattr(response, "status_code", None):
            return f"{type(error).__name__} (HTTP {response.status_code})"
        if isinstance(error, TypeError):
            return f"TypeError: {error}"
        return type(error).__name__

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self._stack is not None:
            await self._stack.__aexit__(
                exc_type,
                exc_value,
                traceback,
            )
            self._stack = None

    def get_openai_tools(self) -> list[dict]:
        return self._openai_tools

    async def call_tool(
        self,
        name: str,
        arguments: dict,
    ) -> str:
        route = self._tool_routes.get(name)

        if route is None:
            raise ValueError(f"Unknown MCP tool: {name}")

        client, original_name = route

        result = await client.call_tool(
            original_name,
            arguments,
        )

        text_parts = [
            item.text for item in result.content if isinstance(item, TextContent)
        ]
        content = "\n".join(text_parts)

        if result.is_error:
            raise RuntimeError(content or f"MCP tool {name!r} failed")

        if content:
            return content

        if result.structured_content is not None:
            return json.dumps(
                result.structured_content,
                ensure_ascii=False,
            )

        return ""
