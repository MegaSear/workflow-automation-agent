import socket
from unittest.mock import MagicMock, patch

import pytest

import react_agent.agent.http_client as http_client
from react_agent.agent.tools.http_get import http_get


@pytest.fixture
def allow_example_host(monkeypatch):
    """Make tests independent of the local .env and host file."""
    monkeypatch.setattr(
        http_client,
        "_allowed_hosts",
        lambda: {"example.com"},
    )


def _dns_record(address: str):
    """Build a getaddrinfo-compatible record."""
    if ":" in address:
        family = socket.AF_INET6
        sockaddr = (address, 443, 0, 0)
    else:
        family = socket.AF_INET
        sockaddr = (address, 443)

    return (
        family,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        sockaddr,
    )


def test_http_get_rejects_http_url():
    assert (
        http_get("http://example.com")
        == "Error: only HTTPS URLs without credentials are allowed"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.com",
        "https://user@example.com",
        "ftp://example.com",
        "https://",
    ],
)
def test_http_get_rejects_unsupported_or_invalid_url(url):
    assert http_get(url) == "Error: only HTTPS URLs without credentials are allowed"


def test_http_get_rejects_unlisted_host_before_dns():
    with (
        patch.object(
            http_client,
            "_allowed_hosts",
            return_value={"trusted.example"},
        ),
        patch.object(http_client, "_resolve_public_ip") as resolve_ip,
    ):
        result = http_get("https://example.com")

    assert result == "Error: host is not in the allowlist"
    resolve_ip.assert_not_called()


def test_http_get_rejects_private_ip(allow_example_host):
    with patch.object(
        http_client.socket,
        "getaddrinfo",
        return_value=[_dns_record("127.0.0.1")],
    ):
        result = http_get("https://example.com")

    assert result == "Error: host resolves to a non-public IP"


def test_http_get_rejects_mixed_public_and_private_ips(
    allow_example_host,
):
    with patch.object(
        http_client.socket,
        "getaddrinfo",
        return_value=[
            _dns_record("93.184.216.34"),
            _dns_record("10.0.0.1"),
        ],
    ):
        result = http_get("https://example.com")

    assert result == "Error: host resolves to a non-public IP"


def test_http_get_handles_empty_dns_result(allow_example_host):
    with patch.object(
        http_client.socket,
        "getaddrinfo",
        return_value=[],
    ):
        result = http_get("https://example.com")

    assert result == "Error: host did not resolve"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:invalid",
        "https://example.com:65536",
    ],
)
def test_http_get_rejects_invalid_port(url, allow_example_host):
    assert http_get(url) == "Error: invalid port"


def test_http_get_rejects_nonstandard_port(allow_example_host):
    with patch.object(http_client, "_resolve_public_ip") as resolve_ip:
        result = http_get("https://example.com:8443")

    assert result == "Error: only port 443 is allowed"
    resolve_ip.assert_not_called()


def test_http_get_returns_body(allow_example_host):
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"hello"

    with (
        patch.object(
            http_client,
            "_resolve_public_ip",
            return_value="93.184.216.34",
        ),
        patch.object(http_client, "_PinnedHTTPSConnection") as connection_cls,
    ):
        connection = connection_cls.return_value
        connection.getresponse.return_value = response

        result = http_get("https://example.com/path?q=1")

    assert result == "HTTP 200\nhello"
    connection.request.assert_called_once_with(
        "GET",
        "/path?q=1",
    )
    connection.close.assert_called_once()


def test_http_get_does_not_follow_redirects(allow_example_host):
    response = MagicMock()
    response.status = 302

    with (
        patch.object(
            http_client,
            "_resolve_public_ip",
            return_value="93.184.216.34",
        ),
        patch.object(http_client, "_PinnedHTTPSConnection") as connection_cls,
    ):
        connection = connection_cls.return_value
        connection.getresponse.return_value = response

        result = http_get("https://example.com")

    assert result == "HTTP error: 302"
    connection.request.assert_called_once()
    response.read.assert_not_called()
    connection.close.assert_called_once()


def test_http_get_rejects_response_over_100_kb(allow_example_host):
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"a" * 100_001

    with (
        patch.object(
            http_client,
            "_resolve_public_ip",
            return_value="93.184.216.34",
        ),
        patch.object(http_client, "_PinnedHTTPSConnection") as connection_cls,
    ):
        connection = connection_cls.return_value
        connection.getresponse.return_value = response

        result = http_get("https://example.com")

    assert result == "Error: response exceeds 100000 bytes"
    response.read.assert_called_once_with(100_001)
    connection.close.assert_called_once()


def test_http_get_handles_network_error(allow_example_host):
    with (
        patch.object(
            http_client,
            "_resolve_public_ip",
            return_value="93.184.216.34",
        ),
        patch.object(http_client, "_PinnedHTTPSConnection") as connection_cls,
    ):
        connection = connection_cls.return_value
        connection.request.side_effect = OSError("Connection refused")

        result = http_get("https://example.com")

    assert result == "Request failed: Connection refused"
    connection.close.assert_called_once()


def test_allowed_hosts_reads_text_file(tmp_path, monkeypatch):
    hosts_file = tmp_path / "http_allowed_hosts.txt"
    hosts_file.write_text(
        """
        API.GITHUB.COM
        api.open-meteo.com
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(http_client.settings, "ALLOWED_HOSTS_FILE", hosts_file)

    assert http_client._allowed_hosts() == {
        "api.github.com",
        "api.open-meteo.com",
    }


def test_allowed_hosts_rejects_empty_file(tmp_path, monkeypatch):
    hosts_file = tmp_path / "http_allowed_hosts.txt"
    hosts_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(http_client.settings, "ALLOWED_HOSTS_FILE", hosts_file)

    with pytest.raises(RuntimeError, match="allowlist is empty"):
        http_client._allowed_hosts()
