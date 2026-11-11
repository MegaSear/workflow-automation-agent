from collections.abc import Sequence

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from react_agent.backend.llm.client import LLMClient
from react_agent.backend.llm.prompts import load_system_prompt, load_tools_policy_prompt

PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_prompt}\n\n{tools_prompt}"),
        MessagesPlaceholder("history"),
        ("human", "{user_input}"),
    ]
)


class Agent:
    def __init__(self, llm: LLMClient):
        self._llm = llm
        self._prompt_template = PROMPT_TEMPLATE

    def build_messages(
        self,
        history: list[dict],
        user_input: str,
    ) -> list[BaseMessage]:
        return self._prompt_template.format_messages(
            system_prompt=load_system_prompt(),
            tools_prompt=load_tools_policy_prompt(),
            history=history,
            user_input=user_input,
        )

    def generate(
        self,
        messages: Sequence[BaseMessage],
        tools: list[dict],
    ):
        return self._llm.generate(messages, tools)
