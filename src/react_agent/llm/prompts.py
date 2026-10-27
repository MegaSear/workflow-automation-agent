from pathlib import Path


PROMPT_DIR = Path(__file__).parent / "prompts"


def load_system_prompt() -> str:
    return (PROMPT_DIR / "system.txt").read_text(encoding="utf-8")


def load_tools_prompt() -> str:
    return (PROMPT_DIR / "tools.txt").read_text(encoding="utf-8")
