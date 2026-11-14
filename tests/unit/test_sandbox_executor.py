import subprocess

import pytest

from react_agent.my_default.docker_proxy import (
    is_allowed_route,
    is_valid_create_request,
)
from react_agent.my_default.sandbox.executor import SandboxExecutor
from react_agent.my_default.sandbox_commands import (
    CREATE_FILE_SCRIPT,
    GIT_STATUS_COMMAND,
)


def test_different_workspaces_use_different_volumes(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[1] == "create":
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=f"{len(commands):064x}\n",
                stderr="",
            )
        if command[1] == "wait":
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="0\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "react_agent.my_default.sandbox.executor.subprocess.run",
        fake_run,
    )

    SandboxExecutor(workspace_id=1)._run("echo", "user-1")
    SandboxExecutor(workspace_id=2)._run("echo", "user-2")

    create_commands = [command for command in commands if command[1] == "create"]
    assert len(create_commands) == 2

    mount_1 = create_commands[0][create_commands[0].index("--mount") + 1]
    mount_2 = create_commands[1][create_commands[1].index("--mount") + 1]

    assert mount_1 == (
        "type=volume,source=react-agent-workspace-user-1,target=/workspace"
    )

    assert mount_2 == (
        "type=volume,source=react-agent-workspace-user-2,target=/workspace"
    )

    assert mount_1 != mount_2


def test_sandbox_execution_uses_detached_lifecycle_and_captures_logs(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        stdout = {
            "create": f"{'a' * 64}\n",
            "wait": "0\n",
            "logs": "sandbox output\n",
        }.get(command[1], "")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(
        "react_agent.my_default.sandbox.executor.subprocess.run",
        fake_run,
    )

    result = SandboxExecutor(workspace_id=7).git_status()

    assert result == {
        "ok": True,
        "stdout": "sandbox output\n",
        "stderr": "",
        "returncode": 0,
    }
    assert [command[1] for command in commands] == [
        "create",
        "start",
        "wait",
        "logs",
        "rm",
    ]


@pytest.mark.parametrize(
    "workspace_id",
    [0, -1, True, "1", None],
)
def test_invalid_workspace_id_is_rejected(workspace_id):
    with pytest.raises(ValueError):
        SandboxExecutor(workspace_id=workspace_id)


def test_workspace_id_is_required():
    with pytest.raises(TypeError):
        SandboxExecutor()


def test_docker_proxy_allows_only_required_routes_for_created_container():
    container_id = "a" * 64

    assert is_allowed_route("GET", "/_ping", set())
    assert is_allowed_route("HEAD", "/_ping", set())
    assert is_allowed_route(
        "GET",
        "/v1.41/images/react-agent-sandbox:latest/json",
        set(),
    )
    assert is_allowed_route(
        "POST",
        f"/v1.41/containers/{container_id}/start",
        {container_id},
    )
    assert is_allowed_route(
        "POST",
        f"/v1.41/containers/{container_id}/attach?stdin=0&stdout=1&stderr=1&stream=1",
        {container_id},
    )
    assert not is_allowed_route(
        "POST",
        f"/v1.41/containers/{container_id}/attach?privileged=1",
        {container_id},
    )
    assert is_allowed_route(
        "GET",
        f"/v1.41/containers/{container_id}/wait?condition=removed",
        {container_id},
    )
    assert is_allowed_route(
        "POST",
        f"/v1.41/containers/{container_id}/wait?condition=not-running",
        {container_id},
    )
    assert is_allowed_route(
        "GET",
        f"/v1.41/containers/{container_id}/logs?stdout=1&stderr=1&follow=0&timestamps=0&since=0&until=0&tail=all",
        {container_id},
    )
    assert not is_allowed_route(
        "GET",
        f"/v1.41/containers/{'b' * 64}/logs?stdout=1&stderr=1&follow=0&timestamps=0&since=0&until=0&tail=all",
        {container_id},
    )
    assert not is_allowed_route(
        "GET",
        f"/v1.41/containers/{container_id}/wait?force=1",
        {container_id},
    )
    assert not is_allowed_route("GET", "/v1.41/containers/json", set())
    assert not is_allowed_route("POST", "/v1.41/containers/prune", set())
    assert not is_allowed_route(
        "POST",
        f"/v1.41/containers/{'b' * 64}/start",
        {container_id},
    )


def test_docker_proxy_accepts_restricted_sandbox_create_request():
    request = {
        "Image": "react-agent-sandbox:latest",
        "User": "runner",
        "Env": [
            "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG=C.UTF-8",
            "GPG_KEY=0123456789abcdef0123456789abcdef01234567",
            "PYTHON_VERSION=3.12.16",
            "PYTHON_SHA256=" + "a" * 64,
        ],
        "WorkingDir": "/workspace",
        "Cmd": GIT_STATUS_COMMAND,
        "Tty": False,
        "OpenStdin": False,
        "HostConfig": {
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": "react-agent-workspace-user-7",
                    "Target": "/workspace",
                }
            ],
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "CgroupnsMode": "private",
            "PidsLimit": 64,
            "Memory": 128 * 1024 * 1024,
            "NanoCpus": 500_000_000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=16m"},
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "AutoRemove": True,
        },
    }

    assert is_valid_create_request(request)
    request["HostConfig"]["SecurityOpt"] = ["no-new-privileges"]
    assert is_valid_create_request(request)


@pytest.mark.parametrize(
    "change",
    [
        lambda request: request.update(Image="untrusted:latest"),
        lambda request: request.update(Cmd=["sh", "-c", "id"]),
        lambda request: request.update(Env=["PYTHONPATH=/workspace"]),
        lambda request: request["HostConfig"].update(NetworkMode="bridge"),
        lambda request: request["HostConfig"].update(Privileged=True),
        lambda request: request["HostConfig"]["Mounts"][0].update(
            Source="/var/run/docker.sock"
        ),
    ],
)
def test_docker_proxy_rejects_unsafe_create_requests(change):
    request = {
        "Image": "react-agent-sandbox:latest",
        "WorkingDir": "/workspace",
        "Cmd": ["python", "-c", CREATE_FILE_SCRIPT, "notes.txt", "safe"],
        "Tty": False,
        "OpenStdin": False,
        "HostConfig": {
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": "react-agent-workspace-user-7",
                    "Target": "/workspace",
                }
            ],
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "CgroupnsMode": "private",
            "PidsLimit": 64,
            "Memory": 128 * 1024 * 1024,
            "NanoCpus": 500_000_000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=16m"},
        },
    }
    change(request)

    assert not is_valid_create_request(request)
