"""
Tests for the LLMClient responsible for communicating with an OpenAI-compatible API.
The tests verify:
- OpenAI client initialization is mocked to avoid real API connections.
- Requests without tools contain only the model and conversation messages.
- Requests with tools include tool definitions and automatic tool selection.
- Empty tool lists are treated as the absence of tools.
- The generate method returns the message from the API response.
All external API interactions are mocked to keep tests deterministic and independent
of network access and API credentials.
"""

from unittest.mock import MagicMock, patch

from react_agent.llm.client import LLMClient


@patch("react_agent.llm.client.OpenAI")
def test_generate_without_tools(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    expected_message = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=expected_message)
    ]

    client = LLMClient()
    messages = [{"role": "user", "content": "Hello"}]

    result = client.generate(messages)

    mock_openai.assert_called_once()
    mock_client.chat.completions.create.assert_called_once_with(
        model=client._model,
        messages=messages,
    )
    assert result is expected_message


@patch("react_agent.llm.client.OpenAI")
def test_generate_with_tools(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    expected_message = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=expected_message)
    ]

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
        tools=tools,
        tool_choice="auto",
    )
    assert result is expected_message


@patch("react_agent.llm.client.OpenAI")
def test_generate_with_empty_tools_does_not_send_tools(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message="response")
    ]

    client = LLMClient()

    result = client.generate(
        [{"role": "user", "content": "Hello"}],
        tools=[],
    )

    mock_client.chat.completions.create.assert_called_once_with(
        model=client._model,
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert result == "response"
