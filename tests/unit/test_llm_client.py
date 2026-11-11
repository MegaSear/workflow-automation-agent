"""
Tests for the LLMClient responsible for communicating with an OpenAI-compatible API.
The tests verify:
- OpenAI client initialization is mocked to avoid real API connections.
- Requests use the configured completion-token limit and sampling parameters.
- Requests forward tool definitions and automatic tool selection.
- Empty tool lists are forwarded as configured.
- The generate method returns the complete API response.
All external API interactions are mocked to keep tests deterministic and independent
of network access and API credentials.
"""

from unittest.mock import MagicMock, patch

from react_agent.backend.llm.client import LLMClient


@patch("react_agent.backend.llm.client.OpenAI")
def test_generate_without_tools(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    expected_response = MagicMock()
    expected_response.choices = [MagicMock(message=MagicMock())]
    mock_client.chat.completions.create.return_value = expected_response

    client = LLMClient()
    messages = [{"role": "user", "content": "Hello"}]

    result = client.generate(messages)

    mock_openai.assert_called_once()
    mock_client.chat.completions.create.assert_called_once_with(
        model=client._model,
        messages=messages,
        max_completion_tokens=1024,
        temperature=None,
        top_p=None,
        frequency_penalty=None,
        presence_penalty=None,
        seed=None,
        reasoning_effort=None,
        parallel_tool_calls=True,
        logprobs=True,
        tools=[],
        tool_choice="auto",
    )
    assert result is expected_response


@patch("react_agent.backend.llm.client.OpenAI")
def test_generate_with_tools(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    expected_response = MagicMock()
    expected_response.choices = [MagicMock(message=MagicMock())]
    mock_client.chat.completions.create.return_value = expected_response

    client = LLMClient()
    messages = [{"role": "user", "content": "Search for a file"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Search files",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    result = client.generate(messages, tools)

    mock_client.chat.completions.create.assert_called_once_with(
        model=client._model,
        messages=messages,
        max_completion_tokens=1024,
        temperature=None,
        top_p=None,
        frequency_penalty=None,
        presence_penalty=None,
        seed=None,
        reasoning_effort=None,
        parallel_tool_calls=True,
        logprobs=True,
        tools=tools,
        tool_choice="auto",
    )
    assert result is expected_response


@patch("react_agent.backend.llm.client.OpenAI")
def test_generate_forwards_configured_sampling_parameters(mock_openai, monkeypatch):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    expected_response = MagicMock()
    expected_response.choices = [MagicMock(message="response")]
    mock_client.chat.completions.create.return_value = expected_response
    monkeypatch.setattr(
        "react_agent.backend.llm.client.settings.LLM_TEMPERATURE",
        0.4,
    )
    monkeypatch.setattr(
        "react_agent.backend.llm.client.settings.LLM_TOP_P",
        0.8,
    )
    monkeypatch.setattr(
        "react_agent.backend.llm.client.settings.LLM_FREQUENCY_PENALTY",
        0.1,
    )
    monkeypatch.setattr(
        "react_agent.backend.llm.client.settings.LLM_PRESENCE_PENALTY",
        0.2,
    )
    monkeypatch.setattr(
        "react_agent.backend.llm.client.settings.LLM_SEED",
        7,
    )
    monkeypatch.setattr(
        "react_agent.backend.llm.client.settings.LLM_REASONING_EFFORT",
        "low",
    )

    client = LLMClient()
    messages = [{"role": "user", "content": "Hello"}]

    client.generate(messages)

    mock_client.chat.completions.create.assert_called_once_with(
        model=client._model,
        messages=messages,
        max_completion_tokens=1024,
        temperature=0.4,
        top_p=0.8,
        frequency_penalty=0.1,
        presence_penalty=0.2,
        seed=7,
        reasoning_effort="low",
        parallel_tool_calls=True,
        logprobs=True,
        tools=[],
        tool_choice="auto",
    )


@patch("react_agent.backend.llm.client.OpenAI")
def test_generate_with_empty_tools_does_not_send_tools(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    expected_response = MagicMock()
    expected_response.choices = [MagicMock(message="response")]
    mock_client.chat.completions.create.return_value = expected_response

    client = LLMClient()

    result = client.generate(
        [{"role": "user", "content": "Hello"}],
        tools=[],
    )

    mock_client.chat.completions.create.assert_called_once_with(
        model=client._model,
        messages=[{"role": "user", "content": "Hello"}],
        max_completion_tokens=1024,
        temperature=None,
        top_p=None,
        frequency_penalty=None,
        presence_penalty=None,
        seed=None,
        reasoning_effort=None,
        parallel_tool_calls=True,
        logprobs=True,
        tools=[],
        tool_choice="auto",
    )
    assert result is expected_response
