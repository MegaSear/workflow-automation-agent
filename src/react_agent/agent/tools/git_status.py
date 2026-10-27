from react_agent.sandbox.executor import SandboxExecutor


def git_status(sandbox: SandboxExecutor) -> str:
    result = sandbox.git_status()
    print(f"[TOOL] git_status -> stdout: {result['stdout'].strip() or '(no output)'}")
    print(
        f"[TOOL] git_status -> stderr: {result.get('stderr', '(empty)').strip() or '(empty)'}"
    )
    print(f"[TOOL] git_status -> exit code: {result.get('returncode', 'N/A')}")

    return str(result)
