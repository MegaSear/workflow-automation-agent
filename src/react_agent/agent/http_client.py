import ipaddress
import socket
import http.client
from react_agent.config import settings
from urllib.parse import urlsplit


def get(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "Error: invalid URL"

    # https без авторизаций
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return "Error: only HTTPS URLs without credentials are allowed"

    try:
        allowed_hosts = _allowed_hosts()
    except RuntimeError as exc:
        return f"Error: {exc}"

    # Фильтрация по доверенным хостам
    if parsed.hostname not in allowed_hosts:
        return "Error: host is not in the allowlist"

    try:
        port = parsed.port
    except ValueError:
        return "Error: invalid port"

    if port is None:
        port = 443

    if port not in settings.ALLOWED_PORTS:
        return "Error: only port 443 is allowed"

    # публичный IP
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
        timeout=settings.REQUEST_TIMEOUT,
    )
    try:
        connection.request("GET", path)
        response = connection.getresponse()

        # если редиректы и ошибки
        if response.status >= 300:
            return f"HTTP error: {response.status}"

        # если слишком тяжёлый ответ
        body = response.read(settings.MAX_BODY_BYTES + 1)
        if len(body) > settings.MAX_BODY_BYTES:
            return (
                f"Error: response exceeds "
                f"{settings.MAX_BODY_BYTES} bytes"
            )
        return (
            f"HTTP {response.status}\n"
            f"{body.decode('utf-8', errors='replace')}"
        )
    except (OSError, http.client.HTTPException) as exc:
        return f"Request failed: {exc}"
    finally:
        connection.close()


def _allowed_hosts() -> set[str]:
    """Load the HTTP hostname allowlist from a text file."""
    try:
        lines = settings.ALLOWED_HOSTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError("HTTP allowlist file cannot be read") from exc

    hosts = {
        line.strip().lower()
        for line in lines
    }
    hosts.discard("")

    if not hosts:
        raise RuntimeError("HTTP allowlist is empty")

    return hosts

def _is_public_ip(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return addr.is_global

def _resolve_public_ip(hostname: str, port: int) -> str:
    """Резолвит хост один раз и возвращает проверенный публичный IP."""
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

    # Проверяем все адреса, а не только тот, к которому подключимся.
    if not all(_is_public_ip(addr) for addr in addresses):
        raise ValueError("host resolves to a non-public IP")

    return str(addresses[0]) # передаём только первый



class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS-соединение на уже проверенный IP.

    Подключение идёт по IP (повторного DNS-запроса нет), а сертификат
    и SNI проверяются по исходному имени хоста.
    """

    def __init__(self, host, pinned_ip, **kwargs):
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise

