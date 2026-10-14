import pytest
from urllib.error import HTTPError, URLError
from react_agent.agent.tools import http_get


def test_http_get_rejects_http_url():
    result = http_get("http://example.com")

    assert result == "Error: only HTTPS URLs without credentials are allowed"


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
    result = http_get(url)

    assert result == "Error: only HTTPS URLs without credentials are allowed"


from unittest.mock import patch


def test_http_get_rejects_private_ip():
    with patch(
        "react_agent.agent.tools.socket.getaddrinfo",
        return_value=[
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    ):
        result = http_get("https://example.com")

    assert result == "Error: host resolves to a non-public IP"


def test_http_get_rejects_host_with_mixed_public_and_private_ips():
    with patch(
        "react_agent.agent.tools.socket.getaddrinfo",
        return_value=[
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("10.0.0.1", 443)),
        ],
    ):
        result = http_get("https://example.com")

    assert result == "Error: host resolves to a non-public IP"


from unittest.mock import MagicMock


def test_http_get_does_not_follow_redirects():
    with (
        patch(
            "react_agent.agent.tools.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ],
        ),
        patch(
            "react_agent.agent.tools.build_opener",
        ) as mock_build_opener,
    ):
        opener = mock_build_opener.return_value
        opener.open.side_effect = HTTPError(
            "https://example.com",
            302,
            "Found",
            {"Location": "https://other.example"},
            None,
        )

        result = http_get("https://example.com")

    assert result == "HTTP error: 302"
    opener.open.assert_called_once()


def test_http_get_rejects_response_over_100_kb():
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"a" * 100_001
    response.__enter__.return_value = response

    with (
        patch(
            "react_agent.agent.tools.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ],
        ),
        patch(
            "react_agent.agent.tools.build_opener",
        ) as mock_build_opener,
    ):
        mock_build_opener.return_value.open.return_value = response

        result = http_get("https://example.com")

    assert result == "Error: response exceeds 100 KB"
    response.read.assert_called_once_with(100_001)


from urllib.error import URLError


def test_http_get_handles_network_error():
    with (
        patch(
            "react_agent.agent.tools.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ],
        ),
        patch(
            "react_agent.agent.tools.build_opener",
        ) as mock_build_opener,
    ):
        mock_build_opener.return_value.open.side_effect = URLError(
            "Connection refused"
        )

        result = http_get("https://example.com")

    assert result == "Request failed: <urlopen error Connection refused>"


def test_http_get_rejects_invalid_port():
    result = http_get("https://example.com:invalid")

    assert result.startswith("Request failed:")


def test_http_get_handles_empty_dns_result():
    with patch(
        "react_agent.agent.tools.socket.getaddrinfo",
        return_value=[],
    ):
        result = http_get("https://example.com")

    assert result == "Error: host resolves to a non-public IP"


def test_http_get_rejects_nonstandard_port():
    with patch(
        "react_agent.agent.tools.socket.getaddrinfo"
    ) as mock_getaddrinfo:
        result = http_get("https://example.com:8443")

    assert result == "Error: only HTTPS port 443 is allowed"
    mock_getaddrinfo.assert_not_called()


def test_http_get_rejects_out_of_range_port():
    result = http_get("https://example.com:65536")

    assert result.startswith("Request failed:")