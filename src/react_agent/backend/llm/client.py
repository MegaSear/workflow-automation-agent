from openai import OpenAI

from react_agent.backend.config import settings


class LLMClient:
    def __init__(self):
        self._client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        self._model = settings.LLM_MODEL

    def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        request = {
            "model": self._model,
            "messages": messages,
            "max_tokens": settings.LLM_MAX_COMPLETION_TOKENS,
        }
        optional_parameters = {
            "temperature": settings.LLM_TEMPERATURE,
            "top_p": settings.LLM_TOP_P,
            "frequency_penalty": settings.LLM_FREQUENCY_PENALTY,
            "presence_penalty": settings.LLM_PRESENCE_PENALTY,
            "seed": settings.LLM_SEED,
            "reasoning_effort": settings.LLM_REASONING_EFFORT,
        }
        request.update(
            {
                name: value
                for name, value in optional_parameters.items()
                if value is not None
            }
        )
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        response = self._client.chat.completions.create(
            **request,
        )
        return response.choices[0].message
