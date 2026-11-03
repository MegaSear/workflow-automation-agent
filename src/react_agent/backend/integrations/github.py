import httpx


def validate_github_token(token: str) -> bool:
    try:
        response = httpx.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            },
            timeout=15.0,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        raise ValueError("Unable to reach the GitHub API") from error

    if response.status_code in {401, 403}:
        return False
    if response.is_error:
        raise ValueError("GitHub API rejected the connection check")
    return True
