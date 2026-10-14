from react_agent.sandbox.executor import SandboxExecutor

def read_file(sandbox: SandboxExecutor, path: str) -> str:
    result = sandbox.read_file(path)
    print(f"[TOOL] read_file -> {result}")
    return str(result)
