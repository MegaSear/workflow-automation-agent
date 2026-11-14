import http.client
import json
import os
import re
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from react_agent.my_default.sandbox_commands import is_allowed_command

DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "react-agent-sandbox:latest")
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MEMORY_BYTES = 128 * 1024 * 1024
MAX_NANO_CPUS = 500_000_000
WORKSPACE_VOLUME_PATTERN = re.compile(r"react-agent-workspace-user-[1-9][0-9]*\Z")
CONTAINER_ID_PATTERN = re.compile(r"[a-f0-9]{12,64}\Z")
API_PATH_PATTERN = re.compile(r"/v[0-9]+\.[0-9]+(/.*)\Z")
PYTHON_VERSION_PATTERN = re.compile(r"3\.12(?:\.[0-9]+)?\Z")
HEX_VALUE_PATTERN = re.compile(r"[a-fA-F0-9]{40,64}\Z")
SAFE_PATH_ENTRIES = {
    "/usr/local/bin",
    "/usr/local/sbin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
}


def _is_safe_sandbox_environment(environment: object) -> bool:
    if environment is None:
        return True
    if not isinstance(environment, list) or not all(
        isinstance(item, str) and "=" in item for item in environment
    ):
        return False

    values = {}
    for item in environment:
        key, value = item.split("=", 1)
        if key in values:
            return False
        values[key] = value

    if set(values) - {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256"}:
        return False
    path = values.get("PATH")
    if path is not None and not set(path.split(":")) <= SAFE_PATH_ENTRIES:
        return False
    if values.get("LANG", "C.UTF-8") != "C.UTF-8":
        return False
    if "GPG_KEY" in values and HEX_VALUE_PATTERN.fullmatch(values["GPG_KEY"]) is None:
        return False
    if (
        "PYTHON_VERSION" in values
        and PYTHON_VERSION_PATTERN.fullmatch(values["PYTHON_VERSION"]) is None
    ):
        return False
    return (
        "PYTHON_SHA256" not in values
        or HEX_VALUE_PATTERN.fullmatch(values["PYTHON_SHA256"]) is not None
    )


def _query_is_allowed(query: str, allowed: dict[str, set[str]]) -> bool:
    try:
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    return all(
        key in allowed and len(items) == 1 and items[0] in allowed[key]
        for key, items in values.items()
    )


def is_allowed_route(method: str, target: str, container_ids: set[str]) -> bool:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or ".." in unquote(parsed.path).split("/"):
        return False

    path = parsed.path
    if (
        method in {"GET", "HEAD"}
        and path in {"/_ping", "/version"}
        and not parsed.query
    ):
        return True

    versioned = API_PATH_PATTERN.fullmatch(path)
    if versioned is None:
        return False
    route = versioned.group(1)

    if method == "GET" and route == "/version" and not parsed.query:
        return True
    if method == "GET" and route == f"/images/{SANDBOX_IMAGE}/json":
        return not parsed.query
    if method == "GET" and unquote(route) == f"/images/{SANDBOX_IMAGE}/json":
        return not parsed.query
    if method == "POST" and route == "/containers/create":
        return not parsed.query

    match = re.fullmatch(r"/containers/([a-f0-9]{12,64})/(attach|start|wait)", route)
    if match and match.group(1) in container_ids:
        action = match.group(2)
        if action == "attach":
            if method != "POST":
                return False
            return _query_is_allowed(
                parsed.query,
                {
                    key: {"0", "1"}
                    for key in ("stream", "stdin", "stdout", "stderr", "logs")
                },
            )
        if action == "start":
            if method != "POST":
                return False
            return _query_is_allowed(
                parsed.query,
                {
                    "detach": {"true", "false"},
                    "detachKeys": {"ctrl-c", "ctrl-p,ctrl-q"},
                },
            )
        return method in {"GET", "POST"} and _query_is_allowed(
            parsed.query, {"condition": {"not-running", "next-exit", "removed"}}
        )

    match = re.fullmatch(r"/containers/([a-f0-9]{12,64})/json", route)
    if match and match.group(1) in container_ids and method == "GET":
        return not parsed.query

    match = re.fullmatch(r"/containers/([a-f0-9]{12,64})/logs", route)
    if match and match.group(1) in container_ids and method == "GET":
        return _query_is_allowed(
            parsed.query,
            {
                "stdout": {"0", "1"},
                "stderr": {"0", "1"},
                "follow": {"0"},
                "timestamps": {"0"},
                "since": {"0"},
                "until": {"0"},
                "tail": {"all"},
            },
        )

    match = re.fullmatch(r"/containers/([a-f0-9]{12,64})", route)
    if match and match.group(1) in container_ids and method == "DELETE":
        return _query_is_allowed(
            parsed.query,
            {"force": {"0", "1"}, "v": {"0", "1"}},
        )
    return False


def create_request_rejection(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "invalid JSON object"

    config = payload.get("Config", payload)
    host = payload.get("HostConfig", config.get("HostConfig", {}))
    if not isinstance(config, dict) or not isinstance(host, dict):
        return "missing container or host configuration"

    image = config.get("Image", payload.get("Image"))
    working_dir = config.get("WorkingDir", payload.get("WorkingDir"))
    user = config.get("User", payload.get("User"))
    entrypoint = config.get("Entrypoint", payload.get("Entrypoint"))
    env = config.get("Env", payload.get("Env"))
    volumes = config.get("Volumes", payload.get("Volumes"))
    tty = config.get("Tty", payload.get("Tty"))
    open_stdin = config.get("OpenStdin", payload.get("OpenStdin"))
    cmd = config.get("Cmd", payload.get("Cmd"))

    if image != SANDBOX_IMAGE:
        return "image is not the configured sandbox image"
    if working_dir != "/workspace":
        return "working directory must be /workspace"
    if user not in (None, "", "runner") or entrypoint not in (None, [], ""):
        return "container user or entrypoint is not allowed"
    if not _is_safe_sandbox_environment(env):
        return "container environment is not allowed"
    if volumes not in (None, {}):
        return "container-defined volumes are not allowed"
    if tty is True or open_stdin is True:
        return "interactive container settings are not allowed"
    if not is_allowed_command(cmd):
        return "container command is not allowlisted"

    mounts = host.get("Mounts")
    if not isinstance(mounts, list) or len(mounts) != 1:
        return "exactly one workspace volume is required"
    mount = mounts[0]
    if not isinstance(mount, dict):
        return "workspace mount is invalid"
    if (
        mount.get("Type") != "volume"
        or not isinstance(mount.get("Source"), str)
        or WORKSPACE_VOLUME_PATTERN.fullmatch(mount["Source"]) is None
        or mount.get("Target") != "/workspace"
        or mount.get("ReadOnly") is True
    ):
        return "workspace volume is not allowed"

    if host.get("NetworkMode") != "none" or host.get("ReadonlyRootfs") is not True:
        return "network isolation and read-only root filesystem are required"
    if host.get("CapDrop") != ["ALL"] or host.get("CapAdd") not in (None, []):
        return "container capabilities are not restricted"
    if host.get("SecurityOpt") not in (
        ["no-new-privileges"],
        ["no-new-privileges:true"],
    ):
        return "security options are not restricted"
    if host.get("CgroupnsMode") != "private":
        return "private cgroup namespace is required"
    if host.get("PidMode") not in (None, ""):
        return "host PID namespace is not allowed"
    if host.get("IpcMode") not in (None, "", "private"):
        return "host IPC namespace is not allowed"
    if host.get("UTSMode") not in (None, ""):
        return "host UTS namespace is not allowed"
    if host.get("UsernsMode") not in (None, ""):
        return "custom user namespace is not allowed"
    pids_limit = host.get("PidsLimit")
    memory_limit = host.get("Memory")
    nano_cpus = host.get("NanoCpus")
    if (
        not isinstance(pids_limit, int)
        or isinstance(pids_limit, bool)
        or pids_limit not in range(1, 65)
    ):
        return "process limit is invalid"
    if (
        not isinstance(memory_limit, int)
        or isinstance(memory_limit, bool)
        or memory_limit not in range(1, MAX_MEMORY_BYTES + 1)
    ):
        return "memory limit is invalid"
    if (
        not isinstance(nano_cpus, int)
        or isinstance(nano_cpus, bool)
        or nano_cpus not in range(1, MAX_NANO_CPUS + 1)
    ):
        return "CPU limit is invalid"
    if host.get("Tmpfs") != {"/tmp": "rw,noexec,nosuid,size=16m"}:
        return "temporary filesystem is not restricted"

    forbidden_host_options = (
        "Privileged",
        "Binds",
        "Devices",
        "DeviceRequests",
        "GroupAdd",
        "PortBindings",
        "VolumesFrom",
        "Links",
        "PublishAllPorts",
        "Sysctls",
        "OomKillDisable",
        "CgroupParent",
        "StorageOpt",
    )
    for key in forbidden_host_options:
        if host.get(key) not in (None, False, [], {}, ""):
            return f"host option {key} is not allowed"
    if host.get("Runtime") not in (None, "", "runc"):
        return "container runtime is not allowed"

    restart_policy = host.get("RestartPolicy", {})
    if not isinstance(restart_policy, dict) or restart_policy.get("Name", "") not in (
        "",
        "no",
    ):
        return "container restart policy is not allowed"
    return None


def is_valid_create_request(payload: object) -> bool:
    return create_request_rejection(payload) is None


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 30):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


class DockerProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    container_ids: set[str] = set()
    container_ids_lock = threading.Lock()

    def log_message(self, _format: str, *args: object) -> None:
        print(f"docker-proxy: {self.client_address[0]} {args[0]}", flush=True)

    def _reject(self, status: int, message: str) -> None:
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _handle_request(self) -> None:
        request_length = self.headers.get("Content-Length", "0")
        if not request_length.isdecimal() or int(request_length) > MAX_REQUEST_BYTES:
            self._reject(413, "Request body too large")
            return
        if self.headers.get("Transfer-Encoding"):
            self._reject(400, "Transfer-Encoding is not supported")
            return

        body = self.rfile.read(int(request_length)) if int(request_length) else b""
        if self.command == "POST" and urlsplit(self.path).path.endswith("/attach"):
            print(
                "docker-proxy: attach headers "
                f"connection={self.headers.get('Connection', '')!r} "
                f"upgrade={self.headers.get('Upgrade', '')!r}",
                flush=True,
            )
        with self.container_ids_lock:
            known_ids = set(self.container_ids)
        if not is_allowed_route(self.command, self.path, known_ids):
            self._reject(403, "Docker API route is not allowed")
            return

        parsed = urlsplit(self.path)
        if self.command == "POST" and parsed.path.endswith("/containers/create"):
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._reject(400, "Invalid JSON body")
                return
            rejection_reason = create_request_rejection(payload)
            if rejection_reason is not None:
                print(f"docker-proxy: rejected create: {rejection_reason}", flush=True)
                self._reject(403, "Container configuration is not allowed")
                return

        if self.command == "POST" and parsed.path.endswith("/attach"):
            if body:
                self._reject(400, "Attach request body must be empty")
                return

            try:
                self._proxy_attach()
            except (OSError, ValueError) as error:
                print(
                    "docker-proxy: attach upstream failure: "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )
                self._reject(502, f"Docker attach unavailable: {type(error).__name__}")
            return

        upstream_timeout = None if parsed.path.endswith("/wait") else 30
        upstream = UnixHTTPConnection(DOCKER_SOCKET, timeout=upstream_timeout)
        upstream_stage = "send request"
        try:
            upstream.request(
                self.command,
                self.path,
                body=body,
                headers={
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in {"host", "expect"}
                },
            )
            upstream_stage = "wait for response headers"
            response = upstream.getresponse()
            if response.status == 101:
                self.send_response(response.status, response.reason)
                for key, value in response.getheaders():
                    if key.lower() not in {"connection", "upgrade"}:
                        self.send_header(key, value)
                self.send_header("Connection", "Upgrade")
                self.send_header("Upgrade", "tcp")
                self.end_headers()
                self.wfile.flush()
                self._tunnel(upstream.sock)
                return

            if self.command == "POST" and parsed.path.endswith("/attach"):
                upstream_stage = "stream attach response"
                self.send_response(response.status, response.reason)
                for key, value in response.getheaders():
                    if key.lower() not in {
                        "connection",
                        "content-length",
                        "transfer-encoding",
                        "date",
                        "server",
                    }:
                        self.send_header(key, value)
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.flush()

                total_bytes = 0
                while chunk := response.read1(65536):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_RESPONSE_BYTES:
                        print(
                            "docker-proxy: attach response limit exceeded", flush=True
                        )
                        return
                    self.wfile.write(chunk)
                    self.wfile.flush()
                return

            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(response_body) > MAX_RESPONSE_BYTES:
                self._reject(502, "Docker API response too large")
                return

            if self.command == "POST" and parsed.path.endswith("/containers/create"):
                if response.status == 201:
                    try:
                        container_id = json.loads(response_body).get("Id", "")
                    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                        container_id = ""
                    if isinstance(container_id, str) and CONTAINER_ID_PATTERN.fullmatch(
                        container_id
                    ):
                        with self.container_ids_lock:
                            self.container_ids.add(container_id)
            if self.command == "DELETE" and 200 <= response.status < 300:
                match = re.search(r"/containers/([a-f0-9]{12,64})\Z", parsed.path)
                if match:
                    with self.container_ids_lock:
                        self.container_ids.discard(match.group(1))

            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in {
                    "connection",
                    "content-length",
                    "transfer-encoding",
                    "date",
                    "server",
                }:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response_body)
        except (OSError, http.client.HTTPException) as error:
            print(
                f"docker-proxy: upstream failure during {upstream_stage}: "
                f"{self.path}: {type(error).__name__}: {error}",
                flush=True,
            )
            self._reject(502, f"Docker daemon unavailable: {type(error).__name__}")
        finally:
            upstream.close()

    def _tunnel(self, upstream_socket: socket.socket | None) -> None:
        if upstream_socket is None:
            return
        client_socket = self.connection
        sockets = [client_socket, upstream_socket]
        while True:
            readable, _, exceptional = select.select(sockets, [], sockets, 60)
            if exceptional or not readable:
                return
            for source in readable:
                destination = (
                    upstream_socket if source is client_socket else client_socket
                )
                try:
                    chunk = source.recv(65536)
                except OSError:
                    return
                if not chunk:
                    return
                try:
                    destination.sendall(chunk)
                except OSError:
                    return

    def _proxy_attach(self) -> None:
        upstream_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        upstream_socket.settimeout(30)
        try:
            upstream_socket.connect(DOCKER_SOCKET)
            request = (
                f"POST {self.path} HTTP/1.1\r\n"
                "Host: docker\r\n"
                "Connection: Upgrade\r\n"
                "Upgrade: tcp\r\n"
                "Content-Length: 0\r\n\r\n"
            ).encode("ascii")
            upstream_socket.sendall(request)

            response_headers = bytearray()
            while not response_headers.endswith(b"\r\n\r\n"):
                byte = upstream_socket.recv(1)
                if not byte:
                    raise ConnectionError("Docker daemon closed attach handshake")
                response_headers.extend(byte)
                if len(response_headers) > 65536:
                    raise ValueError("Docker attach headers are too large")
        except (OSError, ValueError):
            upstream_socket.close()
            raise

        lines = bytes(response_headers).decode("latin-1").split("\r\n")
        status_parts = lines[0].split(" ", 2)
        if len(status_parts) < 2 or not status_parts[1].isdigit():
            upstream_socket.close()
            raise ValueError("Invalid Docker attach response")
        print(f"docker-proxy: attach upstream status {status_parts[1]}", flush=True)

        if status_parts[1] == "101":
            self.connection.sendall(response_headers)
            upstream_socket.settimeout(None)
            self._tunnel(upstream_socket)
            upstream_socket.close()
            return

        self.send_response(
            int(status_parts[1]), status_parts[2] if len(status_parts) > 2 else ""
        )
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                self.send_header(key, value.strip())
        self.end_headers()
        self.wfile.flush()
        upstream_socket.settimeout(None)
        self._tunnel(upstream_socket)
        upstream_socket.close()

    do_GET = _handle_request
    do_HEAD = _handle_request
    do_POST = _handle_request
    do_DELETE = _handle_request


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 2375), DockerProxyHandler)
    print("docker-proxy listening on :2375", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
