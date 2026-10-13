import subprocess

import pytest

from react_agent.sandbox.executor import SandboxExecutor


def test_different_workspaces_use_different_volumes(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "react_agent.sandbox.executor.subprocess.run",
        fake_run,
    )

    SandboxExecutor(workspace_id=1)._run("echo", "user-1")
    SandboxExecutor(workspace_id=2)._run("echo", "user-2")

    assert len(commands) == 2

    mount_1 = commands[0][commands[0].index("--mount") + 1]
    mount_2 = commands[1][commands[1].index("--mount") + 1]

    assert mount_1 == (
        "type=volume,"
        "source=react-agent-workspace-user-1,"
        "target=/workspace"
    )

    assert mount_2 == (
        "type=volume,"
        "source=react-agent-workspace-user-2,"
        "target=/workspace"
    )

    assert mount_1 != mount_2


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