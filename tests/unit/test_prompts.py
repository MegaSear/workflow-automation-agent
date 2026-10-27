
import pytest

from react_agent.llm import prompts


def test_load_system_prompt_reads_file(monkeypatch, tmp_path):
    prompt_file = tmp_path / "system.txt"
    prompt_file.write_text("You are a helpful assistant.", encoding="utf-8")

    monkeypatch.setattr(prompts, "PROMPT_DIR", tmp_path)

    result = prompts.load_system_prompt()

    assert result == "You are a helpful assistant."


def test_load_system_prompt_raises_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "PROMPT_DIR", tmp_path)

    with pytest.raises(FileNotFoundError):
        prompts.load_system_prompt()
