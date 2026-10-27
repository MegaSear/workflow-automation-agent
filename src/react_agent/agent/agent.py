from react_agent.llm.client import LLMClient
from react_agent.llm.prompts import load_system_prompt, load_tools_prompt


class Agent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def build_messages(
        self,
        history: list[dict],
        user_input: str,
    ) -> list[dict]:
        system_prompt = load_system_prompt()
        tools_prompt = load_tools_prompt()
        return [
            {
                "role": "system",
                "content": system_prompt + "\n\n" + tools_prompt,
            },
            *history,
            {
                "role": "user",
                "content": user_input,
            },
        ]

    def generate(
        self,
        messages: list[dict],
        tools: list[dict],
    ):
        return self._llm.generate(messages, tools)


# Заменить Agent на Core, по ТЗ
