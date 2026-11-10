from react_agent.backend.agent.agent import Agent


def test_build_messages_preserves_complete_history(monkeypatch):
    monkeypatch.setattr(
        "react_agent.backend.agent.agent.load_system_prompt",
        lambda: "system",
    )
    monkeypatch.setattr(
        "react_agent.backend.agent.agent.load_tools_prompt",
        lambda: "tools",
    )
    history = [
        {"role": "user", "content": "old request " * 250},
        {"role": "assistant", "content": "old response " * 125},
        {"role": "user", "content": "recent request"},
        {"role": "assistant", "content": "recent response"},
    ]

    messages = Agent(llm=None).build_messages(history, "current request")

    assert messages == [
        {"role": "system", "content": "system\n\ntools"},
        {"role": "user", "content": "old request " * 250},
        {"role": "assistant", "content": "old response " * 125},
        {"role": "user", "content": "recent request"},
        {"role": "assistant", "content": "recent response"},
        {"role": "user", "content": "current request"},
    ]
