from datetime import datetime
from react_agent.sandbox.executor import SandboxExecutor
import ipaddress
import socket
from urllib.parse import urlsplit

import http.client
from urllib.parse import urlsplit
from react_agent.config import settings


ALLOWED_PORTS = {443}
REQUEST_TIMEOUT = 10
MAX_BODY_BYTES = 100_000


def _allowed_hosts() -> set[str]:
    raw = settings.HTTP_ALLOWED_HOSTS
    return {host.strip().lower() for host in raw.split(",") if host.strip()}


def _is_public_ip(addr) -> bool:
    return addr.is_global


def _resolve_public_ip(hostname: str, port: int) -> str:
    """Резолвит хост ОДИН раз и возвращает проверенный публичный IP."""
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)

    addresses = []
    for info in infos:
        raw = info[4][0].split("%")[0]  # убрать zone id у IPv6
        addr = ipaddress.ip_address(raw)
        if addr.version == 6 and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped  # ::ffff:127.0.0.1 -> 127.0.0.1
        addresses.append(addr)

    if not addresses:
        raise ValueError("host did not resolve")

    # Проверяем ВСЕ адреса, а не только тот, к которому подключимся.
    if not all(_is_public_ip(addr) for addr in addresses):
        raise ValueError("host resolves to a non-public IP")

    return str(addresses[0])


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS-соединение на уже проверенный IP.

    Подключение идёт по IP (повторного DNS-запроса нет), а сертификат
    и SNI проверяются по исходному имени хоста.
    """

    def __init__(self, host, pinned_ip, **kwargs):
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self):
        sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )
        try:
            self.sock = self._context.wrap_socket(
                sock, server_hostname=self.host
            )
        except Exception:
            sock.close()
            raise


def http_get(url: str) -> str:
    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return "Error: only HTTPS URLs without credentials are allowed"

    # Точное совпадение имени хоста (urlsplit уже приводит его к нижнему
    # регистру). Проверка идёт ДО DNS-запроса: чужой хост даже не резолвится.
    if parsed.hostname not in _allowed_hosts():
        return "Error: host is not in the allowlist"

    try:
        port = parsed.port or 443
    except ValueError:
        return "Error: invalid port"

    if port not in ALLOWED_PORTS:
        return "Error: only port 443 is allowed"

    try:
        ip = _resolve_public_ip(parsed.hostname, port)
    except ValueError as exc:
        return f"Error: {exc}"
    except OSError as exc:
        return f"Request failed: {exc}"

    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    connection = _PinnedHTTPSConnection(
        parsed.hostname,
        pinned_ip=ip,
        port=port,
        timeout=REQUEST_TIMEOUT,
    )
    try:
        connection.request(
            "GET", path, headers={"User-Agent": "ReactAgent/1.0"}
        )
        response = connection.getresponse()

        # Редиректы не выполняются: http.client их сам не следует.
        if response.status >= 300:
            return f"HTTP error: {response.status}"

        body = response.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            return "Error: response exceeds 100 KB"

        return (
            f"HTTP {response.status}\n"
            f"{body.decode('utf-8', errors='replace')}"
        )
    except (OSError, http.client.HTTPException) as exc:
        return f"Request failed: {exc}"
    finally:
        connection.close()


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
            "description": "Выполнить HTTPS GET-запрос к публичному API из списка разрешённых "
                "хостов, без следования редиректам. Запросы к другим хостам "
                "отклоняются.",
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

