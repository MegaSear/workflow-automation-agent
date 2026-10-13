from datetime import datetime
from react_agent.sandbox.executor import SandboxExecutor
import ipaddress
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

def get_current_time() -> str:
    """Возвращает текущее локальное время сервера."""
    result = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    print(f"[TOOL] get_current_time -> {result}")
    return result

def git_status(sandbox: SandboxExecutor) -> str:
    result = sandbox.git_status()
    print(f"[TOOL] git_status -> stdout: {result['stdout'].strip() or '(no output)'}")
    print(f"[TOOL] git_status -> stderr: {result.get('stderr', '(empty)').strip() or '(empty)'}")
    print(f"[TOOL] git_status -> exit code: {result.get('returncode', 'N/A')}")

    return str(result)


def create_file(sandbox: SandboxExecutor, path: str, content: str) -> str:
    result = sandbox.create_file(path, content)
    print(f"[TOOL] create_file -> {result}")
    return str(result)

def read_file(sandbox: SandboxExecutor, path: str) -> str:
    result = sandbox.read_file(path)
    print(f"[TOOL] read_file -> {result}")
    return str(result)

def http_get(url: str) -> str:
    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return "Error: only HTTPS URLs without credentials are allowed"

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname, 443, type=socket.SOCK_STREAM
            )
        }

        if not addresses or any(
            not ipaddress.ip_address(address).is_global
            for address in addresses
        ):
            return "Error: host resolves to a non-public IP"

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        request = Request(
            url,
            headers={"User-Agent": "ReactAgent/1.0"},
            method="GET",
        )

        with build_opener(NoRedirect).open(request, timeout=10) as response:
            body = response.read(100_001)
            if len(body) > 100_000:
                return "Error: response exceeds 100 KB"

            return (
                f"HTTP {response.status}\n"
                f"{body.decode('utf-8', errors='replace')}"
            )

    except HTTPError as exc:
        return f"HTTP error: {exc.code}"
    except (URLError, OSError, ValueError) as exc:
        return f"Request failed: {exc}"


# Описание функции, которое увидит LLM.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Получить текущее локальное время сервера. "
                "Вызывай, если пользователь просит узнать время "
                "или проверить работу инструмента."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": (
                "Проверить состояние Git-репозитория "
                "в изолированном контейнере. "
                "Не изменяет файлы."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Создать новый файл в изолированной рабочей области. Не перезаписывает существующие файлы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Выполнить HTTPS GET-запрос к публичному API без следования редиректам.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file inside the sandbox workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to /workspace.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


# Allowlist: модель может вызывать только зарегистрированные функции.
TOOL_HANDLERS = {
    "get_current_time": get_current_time,
    "git_status": git_status,
    "create_file": create_file,
    "http_get": http_get,
    "read_file": read_file,
}

SANDBOX_TOOL_NAMES = frozenset({
    "git_status",
    "create_file",
    "read_file",
})

def execute_tool(name: str, arguments: dict, *, workspace_id: int | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)

    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary")
    
    if name in SANDBOX_TOOL_NAMES:
        if workspace_id is None:
            raise ValueError(
                "workspace_id is required for sandbox tools"
            )
        sandbox = SandboxExecutor(workspace_id=workspace_id)
        return handler(sandbox, **arguments)
    
    return handler(**arguments)

