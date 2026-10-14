import json

from react_agent.agent.agent import Agent
from react_agent.agent.tools_compose import execute_tool
from react_agent.agent.tool_schemas import TOOL_SCHEMAS


class Harness:
    def __init__(self, agent: Agent, max_tool_rounds: int = 4):
        self._agent = agent
        self._max_tool_rounds = max_tool_rounds

    def run(
        self,
        history: list[dict],
        user_input: str,
        *,
        workspace_id: int,
    ) -> str:
        messages = self._agent.build_messages(
            history=history,
            user_input=user_input,
        )

        # Несколько итераций: модель -> инструмент -> модель.
        for step in range(self._max_tool_rounds + 1):
            message = self._agent.generate(
                messages=messages,
                tools=TOOL_SCHEMAS,
            )

            tool_calls = message.tool_calls

            # Модель решила, что дополнительных действий не нужно.
            if not tool_calls:
                return message.content or ""

            # Оставляем возможность получить финальный ответ
            # после последнего разрешённого раунда инструментов.
            if step == self._max_tool_rounds:
                return "Превышен лимит вызовов инструментов."

            # Сохраняем запрос модели на вызов инструментов.
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            })

            # Исполняем каждый вызов через allowlist.
            for call in tool_calls:
                name = call.function.name
                print(f"[HARNESS] Calling tool: {name}")

                try:
                    arguments = json.loads(
                        call.function.arguments or "{}"
                    )

                    if not isinstance(arguments, dict):
                        raise ValueError(
                            "Tool arguments must be a JSON object"
                        )

                    result = execute_tool(name, 
                                          arguments,
                                          workspace_id=workspace_id,)
                    content = str(result)        
                except Exception as error:
                    content = f"Tool error: {error}"

                print(
                    f"[HARNESS] Tool {name} result preview: {content[:100]!r}"
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": content,
                })

        return "Не удалось завершить выполнение."
