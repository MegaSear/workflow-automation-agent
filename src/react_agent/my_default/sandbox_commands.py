GIT_STATUS_COMMAND = [
    "git",
    "-c",
    "safe.directory=/workspace",
    "status",
    "--short",
]

CREATE_FILE_SCRIPT = """
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

READ_FILE_SCRIPT = """
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


def is_allowed_command(command: object) -> bool:
    if not isinstance(command, list) or not all(
        isinstance(argument, str) and len(argument) <= 10_000 for argument in command
    ):
        return False

    if command == GIT_STATUS_COMMAND:
        return True

    is_read_file = len(command) == 4 and command[2] == READ_FILE_SCRIPT
    is_create_file = len(command) == 5 and command[2] == CREATE_FILE_SCRIPT
    if not (is_read_file or is_create_file) or command[0:2] != ["python", "-c"]:
        return False

    path = command[3]
    if (
        not path
        or path.startswith(("/", "\\"))
        or ".." in path.replace("\\", "/").split("/")
    ):
        return False

    return not is_create_file or len(command[4]) <= 10_000
