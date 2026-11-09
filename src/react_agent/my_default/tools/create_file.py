from react_agent.my_default.sandbox.executor import SandboxExecutor


def create_file(sandbox: SandboxExecutor, path: str, content: str) -> str:
    result = sandbox.create_file(path, content)
    print(f"[TOOL] create_file -> {result}")
    return str(result)
