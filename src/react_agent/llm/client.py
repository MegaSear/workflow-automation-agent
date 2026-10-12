from openai import OpenAI
from react_agent.config import settings

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
                }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        response = self._client.chat.completions.create(
            **request,
        )
        return response.choices[0].message