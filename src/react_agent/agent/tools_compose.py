from react_agent.sandbox.executor import SandboxExecutor
from react_agent.agent.tool_schemas import TOOL_SCHEMAS
from react_agent.agent.tools.git_status import git_status
from react_agent.agent.tools.create_file import create_file
from react_agent.agent.tools.read_file import read_file
from react_agent.agent.tools.get_current_time import get_current_time
from react_agent.agent.tools.http_get import http_get

TOOL_HANDLERS = {
    "get_current_time": get_current_time,
    "git_status": git_status,
    "create_file": create_file,
    "http_get": http_get,
    "read_file": read_file,
}

SANDBOX_TOOL_NAMES = frozenset({
    "git_status",
    "create_file",
    "read_file",
})

def execute_tool(name: str, arguments: dict, *, workspace_id: int | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)

    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary")
    
    if name in SANDBOX_TOOL_NAMES:
        if workspace_id is None:
            raise ValueError(
                "workspace_id is required for sandbox tools"
            )
        sandbox = SandboxExecutor(workspace_id=workspace_id)
        return handler(sandbox, **arguments)
    
    return handler(**arguments)

