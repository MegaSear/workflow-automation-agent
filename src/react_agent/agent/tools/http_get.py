import react_agent.agent.http_client as http_client


def http_get(url: str) -> str:
    print(f"[TOOL] GET URL -> {url}")
    return http_client.get(url)
