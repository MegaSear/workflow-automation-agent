
import subprocess


SANDBOX_IMAGE = "react-agent-sandbox:latest"
CONTAINER_WORKDIR = "/workspace"
WORKSPACE_VOLUME_PREFIX = "react-agent-workspace-user-"

class SandboxExecutor:
    def __init__(self,
                 workspace_id: int,
                 timeout: int = 10):
        if (
            isinstance(workspace_id, bool)
            or not isinstance(workspace_id, int)
            or workspace_id <= 0
        ):
            raise ValueError(
                "workspace_id must be a positive integer"
            )

        self._workspace_volume = (
            f"{WORKSPACE_VOLUME_PREFIX}{workspace_id}"
        )

        self._timeout = timeout

    def _run(self, *args: str) -> dict:
        command = [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=128m",
            "--cpus=0.5",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--mount",
            f"type=volume,source={self._workspace_volume},target={CONTAINER_WORKDIR}",
            "--workdir", CONTAINER_WORKDIR,
            SANDBOX_IMAGE,
            *args,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Execution timed out"}
        except OSError:
            return {"ok": False, "error": "Failed to start Docker"}

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[:10_000],
            "stderr": result.stderr[:2_000],
            "returncode": result.returncode,
        }

    def git_status(self) -> dict:
        return self._run(
            "git", "-c", "safe.directory=/workspace",
            "status", "--short",
        )

    def create_file(self, path: str, content: str) -> dict:
        script = """
from pathlib import Path
import sys

root = Path("/workspace").resolve()
relative = Path(sys.argv[1])

if relative.is_absolute() or ".." in relative.parts:
    print("Invalid path", file=sys.stderr)
    sys.exit(2)

target = (root / relative).resolve()

if not target.is_relative_to(root) or target == root:
    print("Invalid path", file=sys.stderr)
    sys.exit(2)

if target.exists():
    print("File already exists", file=sys.stderr)
    sys.exit(3)

target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(sys.argv[2], encoding="utf-8")
print(f"Created: {target.relative_to(root)}")
"""
        return self._run("python", "-c", script, path, content)

    def read_file(self, path: str) -> dict:
        script = """
from pathlib import Path
import sys

root = Path("/workspace").resolve()
relative = Path(sys.argv[1])

if relative.is_absolute() or ".." in relative.parts:
    print("Invalid path", file=sys.stderr)
    sys.exit(2)

target = (root / relative).resolve()

if not target.is_relative_to(root) or target == root:
    print("Invalid path", file=sys.stderr)
    sys.exit(2)

if not target.is_file():
    print("File not found", file=sys.stderr)
    sys.exit(4)

if target.stat().st_size > 10_000:
    print("File exceeds 10 KB limit", file=sys.stderr)
    sys.exit(5)

print(target.read_text(encoding="utf-8"), end="")
"""
        return self._run("python", "-c", script, path)