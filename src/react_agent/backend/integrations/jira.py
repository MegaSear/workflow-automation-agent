import base64
import os

from react_agent.backend.mcp.manager import connect_remote_mcp


async def validate_jira_credentials(credentials: dict) -> bool:
    email = credentials.get("email")
    api_token = credentials.get("api_token")
    mcp_url = os.environ.get("JIRA_MCP_URL")

    if not isinstance(email, str) or not email.strip():
        raise ValueError("Jira email is required")

    if not isinstance(api_token, str) or not api_token.strip():
        raise ValueError("Jira API token is required")

    if not mcp_url:
        raise ValueError("JIRA_MCP_URL is not configured")

    encoded = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")

    headers = {
        "Authorization": f"Basic {encoded}",
    }

    try:
        async with connect_remote_mcp(mcp_url, headers=headers) as client:
            result = await client.list_tools()

            if not result.tools:
                raise ValueError("Jira MCP server returned no tools")

    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Unable to connect to Atlassian MCP. "
            "Check credentials and API-token authentication settings."
        ) from error

    return True
