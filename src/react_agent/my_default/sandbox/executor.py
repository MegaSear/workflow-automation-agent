import os
import re
import subprocess
import time

from react_agent.my_default.sandbox_commands import (
    CREATE_FILE_SCRIPT,
    GIT_STATUS_COMMAND,
    READ_FILE_SCRIPT,
)

SANDBOX_IMAGE = os.getenv(
    "SANDBOX_IMAGE",
    "react-agent-sandbox:latest",
)

CONTAINER_WORKDIR = "/workspace"
WORKSPACE_VOLUME_PREFIX = "react-agent-workspace-user-"


class SandboxExecutor:
    def __init__(self, workspace_id: int, timeout: int = 10):
        if (
            isinstance(workspace_id, bool)
            or not isinstance(workspace_id, int)
            or workspace_id <= 0
        ):
            raise ValueError("workspace_id must be a positive integer")

        self._workspace_volume = f"{WORKSPACE_VOLUME_PREFIX}{workspace_id}"

        self._timeout = timeout

    def _run(self, *args: str) -> dict:
        command = [
            "docker",
            "create",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--cgroupns=private",
            "--pids-limit=64",
            "--memory=128m",
            "--cpus=0.5",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--mount",
            f"type=volume,source={self._workspace_volume},target={CONTAINER_WORKDIR}",
            "--workdir",
            CONTAINER_WORKDIR,
            SANDBOX_IMAGE,
            *args,
        ]

        deadline = time.monotonic() + self._timeout
        created = self._run_docker(command, self._remaining_time(deadline))
        if not created["ok"]:
            return created

        container_id = created["stdout"].strip()
        if re.fullmatch(r"[a-f0-9]{12,64}", container_id) is None:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "Docker returned an invalid container ID",
                "returncode": 1,
            }

        try:
            started = self._run_docker(
                ["docker", "start", container_id],
                self._remaining_time(deadline),
            )
            if not started["ok"]:
                return started

            waited = self._run_docker(
                ["docker", "wait", container_id],
                self._remaining_time(deadline),
            )
            if not waited["ok"]:
                return waited

            try:
                exit_code = int(waited["stdout"].strip())
            except ValueError:
                return {
                    "ok": False,
                    "stdout": "",
                    "stderr": "Docker returned an invalid container exit code",
                    "returncode": 1,
                }

            logs = self._run_docker(
                ["docker", "logs", container_id],
                self._remaining_time(deadline),
            )
            if not logs["ok"]:
                return logs

            return {
                "ok": exit_code == 0,
                "stdout": logs["stdout"][:10_000],
                "stderr": logs["stderr"][:2_000],
                "returncode": exit_code,
            }
        finally:
            self._run_docker(
                ["docker", "rm", "--force", container_id],
                timeout=min(self._timeout, 2),
            )

    @staticmethod
    def _remaining_time(deadline: float) -> float:
        return max(0.1, deadline - time.monotonic())

    @staticmethod
    def _run_docker(command: list[str], timeout: float) -> dict:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "Execution timed out",
                "returncode": 1,
                "error": "Execution timed out",
            }
        except OSError:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "Failed to start Docker",
                "returncode": 1,
                "error": "Failed to start Docker",
            }

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[:10_000],
            "stderr": result.stderr[:2_000],
            "returncode": result.returncode,
        }

    def git_status(self) -> dict:
        return self._run(*GIT_STATUS_COMMAND)

    def create_file(self, path: str, content: str) -> dict:
        return self._run("python", "-c", CREATE_FILE_SCRIPT, path, content)

    def read_file(self, path: str) -> dict:
        return self._run("python", "-c", READ_FILE_SCRIPT, path)
