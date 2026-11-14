import json
from unittest.mock import MagicMock

import react_agent.my_default.http_client as http_client
from react_agent.my_default.tools.http_get import http_get


def test_http_get_fetches_from_allowlisted_api(monkeypatch):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=52.52&longitude=13.41&current=temperature_2m"
    )
    expected_payload = {"current": {"temperature_2m": 18.5}}
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps(expected_payload).encode("utf-8")
    connection = MagicMock()
    connection.getresponse.return_value = response

    monkeypatch.setattr(
        http_client,
        "_allowed_hosts",
        lambda: {"api.open-meteo.com"},
    )
    monkeypatch.setattr(
        http_client,
        "_resolve_public_ip",
        lambda hostname, port: "93.184.216.34",
    )
    monkeypatch.setattr(
        http_client,
        "_PinnedHTTPSConnection",
        lambda *args, **kwargs: connection,
    )

    result = http_get(url)

    status, separator, body = result.partition("\n")

    assert separator, f"Unexpected result: {result}"
    assert status == "HTTP 200", f"Request failed: {result}"

    payload = json.loads(body)

    assert payload == expected_payload
    connection.request.assert_called_once_with(
        "GET",
        "/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m",
    )
