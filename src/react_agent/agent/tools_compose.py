from sqlalchemy.orm import Session

from react_agent.agent.tools.create_file import create_file
from react_agent.agent.tools.get_current_time import get_current_time
from react_agent.agent.tools.git_status import git_status
from react_agent.agent.tools.google_calendar import (
    calendar_list_events,
)
from react_agent.agent.tools.http_get import http_get
from react_agent.agent.tools.jira import (
    jira_get_issue,
    jira_search_issues,
)
from react_agent.agent.tools.read_file import read_file
from react_agent.sandbox.executor import SandboxExecutor

TOOL_HANDLERS = {
    "get_current_time": get_current_time,
    "git_status": git_status,
    "create_file": create_file,
    "http_get": http_get,
    "read_file": read_file,
    "jira_get_issue": jira_get_issue,
    "jira_search_issues": jira_search_issues,
    "calendar_list_events": calendar_list_events,
}

SANDBOX_TOOL_NAMES = frozenset(
    {
        "git_status",
        "create_file",
        "read_file",
    }
)

USER_SCOPED_TOOL_NAMES = frozenset(
    {
        "jira_get_issue",
        "jira_search_issues",
        "calendar_list_events",
    }
)


def execute_tool(
    name: str,
    arguments: dict,
    *,
    workspace_id: int | None = None,
    user_id: int | None = None,
    db: Session | None = None,
) -> str:
    handler = TOOL_HANDLERS.get(name)

    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary")

    if name in USER_SCOPED_TOOL_NAMES:
        if user_id is None or db is None:
            raise ValueError("user_id and db are required for integration tools")
        return handler(
            db=db,
            user_id=user_id,
            **arguments,
        )

    if name in SANDBOX_TOOL_NAMES:
        if workspace_id is None:
            raise ValueError("workspace_id is required for sandbox tools")

        sandbox = SandboxExecutor(workspace_id=workspace_id)
        return handler(sandbox, **arguments)

    return handler(**arguments)
