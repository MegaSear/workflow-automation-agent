import json
import re
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from react_agent.integrations.credentials import get_credentials

ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


def _jira_get(
    db: Session,
    *,
    user_id: int,
    path: str,
    params: dict | None = None,
) -> tuple[dict, str]:

    credentials = get_credentials(
        db,
        user_id=user_id,
        provider="jira",
    )

    if credentials is None:
        raise RuntimeError(
            "Jira is not connected. Connect Jira in your account settings."
        )

    base_url = credentials.get("base_url", "").rstrip("/")
    email = credentials.get("email", "")
    token = credentials.get("api_token", "")

    if not all((base_url, email, token)):
        raise RuntimeError(
            "Jira is not configured. Set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN."
        )

    parsed = urlparse(base_url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".atlassian.net")
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid Jira Cloud base URL")

    with httpx.Client(
        base_url=base_url,
        auth=(email, token),
        headers={"Accept": "application/json"},
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json(), base_url


def jira_get_issue(
    issue_key: str,
    *,
    db: Session,
    user_id: int,
) -> str:
    """Get a Jira issue by its key, for example PROJ-123."""

    issue_key = issue_key.strip().upper()

    if not ISSUE_KEY_PATTERN.fullmatch(issue_key):
        raise ValueError("Invalid Jira issue key")

    data, base_url = _jira_get(
        db,
        user_id=user_id,
        path=f"/rest/api/3/issue/{issue_key}",
    )

    fields = data["fields"]

    result = {
        "key": data["key"],
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "assignee": ((fields.get("assignee") or {}).get("displayName")),
        "url": f"{base_url}/browse/{data['key']}",
    }

    return json.dumps(result, ensure_ascii=False)


def jira_search_issues(
    jql: str,
    max_results: int = 10,
    *,
    db: Session,
    user_id: int,
) -> str:
    """Search Jira issues using a read-only JQL query."""

    jql = jql.strip()

    if not jql or len(jql) > 2000:
        raise ValueError("JQL must contain 1-2000 characters")

    if not 1 <= max_results <= 20:
        raise ValueError("max_results must be between 1 and 20")

    data, _ = _jira_get(
        db,
        user_id=user_id,
        path="/rest/api/3/search/jql",
        params={
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee",
        },
    )

    issues = []

    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        issues.append(
            {
                "key": issue["key"],
                "summary": fields.get("summary"),
                "status": ((fields.get("status") or {}).get("name")),
                "assignee": ((fields.get("assignee") or {}).get("displayName")),
            }
        )

    return json.dumps(
        {
            "issues": issues,
            "is_last": data.get("isLast"),
        },
        ensure_ascii=False,
    )


def validate_jira_credentials(
    base_url: str,
    email: str,
    api_token: str,
) -> str:
    base_url = base_url.strip().rstrip("/")
    parsed = urlparse(base_url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".atlassian.net")
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid Jira Cloud base URL")

    if not email.strip() or not api_token:
        raise ValueError("Email and API token are required")

    with httpx.Client(
        base_url=base_url,
        auth=(email.strip(), api_token),
        headers={"Accept": "application/json"},
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get("/rest/api/3/myself")
        response.raise_for_status()

    return base_url
