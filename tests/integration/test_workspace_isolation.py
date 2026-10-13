import secrets
import subprocess

import pytest

from react_agent.sandbox.executor import (
    SANDBOX_IMAGE,
    WORKSPACE_VOLUME_PREFIX,
    SandboxExecutor,
)


def docker_command(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def require_docker_image() -> None:
    try:
        result = docker_command("info")
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker is unavailable")

    if result.returncode != 0:
        pytest.skip("Docker daemon is not running")

    result = docker_command("image", "inspect", SANDBOX_IMAGE)

    if result.returncode != 0:
        pytest.skip(
            "Sandbox image is missing. Build it with: "
            "docker build -t react-agent-sandbox:latest ./sandbox"
        )


def get_fresh_workspace_ids() -> tuple[int, int]:
    for _ in range(10):
        first_id = 1_000_000_000 + secrets.randbelow(
            1_000_000_000
        )
        ids = (first_id, first_id + 1)

        volumes = [
            f"{WORKSPACE_VOLUME_PREFIX}{workspace_id}"
            for workspace_id in ids
        ]

        if all(
            docker_command("volume", "inspect", volume).returncode != 0
            for volume in volumes
        ):
            return ids

    pytest.fail("Could not allocate fresh test workspace IDs")


def test_users_cannot_read_each_others_files():
    require_docker_image()

    user_1_id, user_2_id = get_fresh_workspace_ids()

    volumes = [
        f"{WORKSPACE_VOLUME_PREFIX}{user_1_id}",
        f"{WORKSPACE_VOLUME_PREFIX}{user_2_id}",
    ]

    user_1 = SandboxExecutor(workspace_id=user_1_id)
    user_2 = SandboxExecutor(workspace_id=user_2_id)

    filename = "isolation_probe.txt"

    try:
        # Пользователь 1 создаёт свой секретный файл.
        created = user_1.create_file(
            filename,
            "secret-from-user-1",
        )
        assert created["ok"], created

        # Новый контейнер того же пользователя видит сохранённый файл.
        own_file = user_1.read_file(filename)
        assert own_file["ok"], own_file
        assert own_file["stdout"] == "secret-from-user-1"

        # Пользователь 2 не должен видеть файл пользователя 1.
        other_file = user_2.read_file(filename)

        assert not other_file["ok"], other_file
        assert other_file["returncode"] == 4
        assert "File not found" in other_file["stderr"]

        # Пользователь 2 создаёт собственный файл с тем же именем.
        created = user_2.create_file(
            filename,
            "secret-from-user-2",
        )
        assert created["ok"], created

        own_file = user_2.read_file(filename)
        assert own_file["ok"], own_file
        assert own_file["stdout"] == "secret-from-user-2"

        # Файл пользователя 1 остался независимым.
        own_file = user_1.read_file(filename)
        assert own_file["ok"], own_file
        assert own_file["stdout"] == "secret-from-user-1"

    finally:
        # Удаляем только созданные этим тестом volumes.
        for volume in volumes:
            subprocess.run(
                ["docker", "volume", "rm", volume],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )