import asyncio
import json
import logging
from time import perf_counter

from sqlalchemy.orm import Session

from react_agent.backend.agent.agent import Agent
from react_agent.backend.mcp.manager import MCPManager
from react_agent.backend.mcp.registry import (
    create_mcp_client_factories,
    load_mcp_server_specs,
)
from react_agent.backend.observability.metrics import (
    AGENT_ACTIVE_RUNS,
    AGENT_RUN_DURATION,
    AGENT_RUNS,
    TOOL_CALLS,
    TOOL_DURATION,
)

logger = logging.getLogger(__name__)


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
        user_id: int,
        db: Session,
        tool_trace: list[dict] | None = None,
    ) -> str:
        return asyncio.run(
            self._run_async(
                history=history,
                user_input=user_input,
                workspace_id=workspace_id,
                user_id=user_id,
                db=db,
                tool_trace=tool_trace,
            )
        )

    async def _run_async(
        self,
        history: list[dict],
        user_input: str,
        *,
        workspace_id: int,
        user_id: int,
        db: Session,
        tool_trace: list[dict] | None = None,
    ) -> str:
        started = perf_counter()
        run_status = "error"
        AGENT_ACTIVE_RUNS.inc()

        try:
            server_specs = load_mcp_server_specs()
            remote_clients = create_mcp_client_factories(
                server_specs,
                db=db,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            tool_allowlists = {
                server_name: set(spec["tool_allowlist"])
                for server_name, spec in server_specs.items()
                if isinstance(spec.get("tool_allowlist"), list)
                and all(isinstance(name, str) for name in spec["tool_allowlist"])
            }

            async with MCPManager(
                servers={},
                remote_clients=remote_clients,
                tool_allowlists=tool_allowlists,
            ) as mcp:
                messages = self._agent.build_messages(
                    history=history,
                    user_input=user_input,
                )

                for step in range(self._max_tool_rounds + 1):
                    tools = mcp.get_openai_tools()
                    logger.warning(
                        "LLM payload: messages=%d, tools=%d, tool_names=%s",
                        len(messages),
                        len(tools),
                        [tool["function"]["name"] for tool in tools],
                    )
                    message = self._agent.generate(
                        messages=messages,
                        tools=tools,
                    )

                    tool_calls = message.tool_calls

                    if not tool_calls:
                        run_status = "success"
                        return message.content or ""

                    if step == self._max_tool_rounds:
                        run_status = "limit"
                        return "Превышен лимит вызовов инструментов."

                    messages.append(
                        {
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
                        }
                    )

                    for call in tool_calls:
                        name = call.function.name

                        original_name = name.split("__", maxsplit=1)[-1]
                        metric_tool = original_name

                        tool_started = perf_counter()
                        tool_status = "error"
                        trace_entry = None
                        if tool_trace is not None:
                            trace_entry = {
                                "name": name,
                                "status": "running",
                            }
                            tool_trace.append(trace_entry)

                        try:
                            arguments = json.loads(call.function.arguments or "{}")

                            if not isinstance(arguments, dict):
                                raise ValueError("Tool arguments must be a JSON object")

                            result = await mcp.call_tool(
                                name=name,
                                arguments=arguments,
                            )

                            content = str(result)
                            tool_status = "success"

                        except Exception as error:
                            content = f"Tool error: {error}"

                        finally:
                            TOOL_CALLS.labels(
                                tool=metric_tool,
                                status=tool_status,
                            ).inc()

                            TOOL_DURATION.observe(perf_counter() - tool_started)
                            if trace_entry is not None:
                                trace_entry["status"] = tool_status

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": content,
                            }
                        )

                return "Не удалось завершить выполнение."

        finally:
            AGENT_ACTIVE_RUNS.dec()

            AGENT_RUNS.labels(status=run_status).inc()
            AGENT_RUN_DURATION.observe(perf_counter() - started)
