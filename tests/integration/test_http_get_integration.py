import json
from react_agent.agent.tools.http_get import http_get


def test_http_get_fetches_from_allowlisted_api():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=52.52&longitude=13.41&current=temperature_2m"
    )

    result = http_get(url)

    status, separator, body = result.partition("\n")

    assert separator, f"Unexpected result: {result}"
    assert status == "HTTP 200", f"Request failed: {result}"

    payload = json.loads(body)

    assert isinstance(payload, dict)
    assert isinstance(payload.get("current"), dict)
    assert isinstance(
        payload["current"].get("temperature_2m"),
        (int, float),
    )