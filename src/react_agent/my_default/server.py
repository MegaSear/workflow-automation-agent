import contextvars
import hmac
from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from react_agent.my_default.config import settings
from react_agent.my_default.sandbox.executor import SandboxExecutor
from react_agent.my_default.tools.create_file import (
    create_file as run_create_file,
)
from react_agent.my_default.tools.get_current_time import (
    get_current_time as run_get_current_time,
)
from react_agent.my_default.tools.git_status import (
    git_status as run_git_status,
)
from react_agent.my_default.tools.http_get import (
    http_get as run_http_get,
)
from react_agent.my_default.tools.read_file import (
    read_file as run_read_file,
)

_workspace_id: contextvars.ContextVar[int] = contextvars.ContextVar("workspace_id")


def _sandbox() -> SandboxExecutor:
    return SandboxExecutor(workspace_id=_workspace_id.get())


def create_my_default_server() -> MCPServer:
    server = MCPServer(name="my_default")

    @server.tool()
    def get_current_time() -> str:
        """Get the current local server time."""
        return run_get_current_time()

    @server.tool()
    def git_status() -> str:
        """Check the Git status of the isolated workspace."""
        return run_git_status(_sandbox())

    @server.tool()
    def create_file(path: str, content: str) -> str:
        """Create a new file in the isolated workspace."""
        return run_create_file(_sandbox(), path=path, content=content)

    @server.tool()
    def read_file(path: str) -> str:
        """Read a file from the isolated workspace."""
        return run_read_file(_sandbox(), path=path)

    @server.tool()
    def http_get(url: str) -> str:
        """Perform a secure HTTPS GET request to an allowed public host."""
        return run_http_get(url)

    return server


class _BackendAuthMiddleware:
    def __init__(
        self,
        app: Callable,
        *,
        token: str,
    ):
        self._app = app
        self._token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["path"] not in {"/mcp", "/mcp/"}:
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        supplied_token = authorization.removeprefix("Bearer ")
        raw_workspace_id = headers.get(b"x-workspace-id", b"").decode("ascii", "ignore")
        try:
            workspace_id = int(raw_workspace_id)
        except ValueError:
            workspace_id = 0

        if not hmac.compare_digest(supplied_token, self._token) or workspace_id <= 0:
            response = JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        token = _workspace_id.set(workspace_id)
        try:
            await self._app(scope, receive, send)
        finally:
            _workspace_id.reset(token)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_my_default_app(*, token: str) -> Callable:
    if not token.strip():
        raise ValueError("MY_DEFAULT_MCP_TOKEN must be configured")

    server = create_my_default_server()
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                "my-default:8001",
                "localhost:8001",
                "127.0.0.1:8001",
            ],
        ),
    )
    app.router.routes.append(Route("/health", health, methods=["GET"]))
    return _BackendAuthMiddleware(app, token=token)


app = create_my_default_app(token=settings.MY_DEFAULT_MCP_TOKEN or "")
