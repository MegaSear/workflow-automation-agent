import logging
from collections.abc import Sequence

from langchain_core.messages import (
    BaseMessage,
    convert_to_openai_messages,
)
from openai import OpenAI
from openai.types.chat import ChatCompletion

from react_agent.backend.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key, base_url, max_retries, timeout, llm_model):
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._model = llm_model

    def generate(
        self,
        messages: Sequence[BaseMessage],
        tools: list[dict] = [],
    ) -> ChatCompletion:
        request = {
            # Base
            "model": self._model,
            "messages": convert_to_openai_messages(messages),
            "max_completion_tokens": settings.LLM_MAX_COMPLETION_TOKENS,
            # Parameters
            "temperature": settings.LLM_TEMPERATURE,
            "top_p": settings.LLM_TOP_P,
            "frequency_penalty": settings.LLM_FREQUENCY_PENALTY,
            "presence_penalty": settings.LLM_PRESENCE_PENALTY,
            "seed": settings.LLM_SEED,
            "reasoning_effort": settings.LLM_REASONING_EFFORT,
            "parallel_tool_calls": settings.LLM_PARALLEL_TOOL_CALLS,
            "logprobs": False,
            # Tools Usage
            "tools": tools,
            "tool_choice": "auto",
        }

        response = self._client.chat.completions.create(
            **request,
        )
        return response

    def warmup(
        self,
        messages: Sequence[BaseMessage],
    ) -> ChatCompletion:

        request = {
            "model": self._model,
            "messages": convert_to_openai_messages(messages),
            "max_tokens": 1,
            "temperature": 0,
        }
        response = self._client.chat.completions.create(
            **request,
        )
        if not response.choices:
            raise RuntimeError("LLM warmup returned no choices")
        return response
