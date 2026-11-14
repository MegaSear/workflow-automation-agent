import asyncio
import json
import logging
from time import perf_counter

from langchain_core.messages import AIMessage, ToolMessage
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
    LLM_COMPLETION_TOKENS,
    LLM_FINISH_REASONS,
    LLM_PROMPT_TOKENS,
    TOOL_CALLS,
    TOOL_DURATION,
)
from react_agent.backend.tools.memory.tools import MemoryTools

logger = logging.getLogger(__name__)


def prepare_mcp_clients(db, workspace_id, user_id):
    server_specs = load_mcp_server_specs()
    remote_clients = create_mcp_client_factories(
        server_specs,
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    tool_allowlists = {
        name: set(spec["tool_allowlist"])
        for name, spec in server_specs.items()
        if isinstance(spec.get("tool_allowlist"), list)
        and all(isinstance(item, str) for item in spec["tool_allowlist"])
    }
    db.rollback()
    return remote_clients, tool_allowlists


class Harness:
    def __init__(
        self,
        agent: Agent,
        max_tool_rounds: int = 4,
        memory_tools: MemoryTools | None = None,
    ):
        self._agent = agent
        self._max_tool_rounds = max_tool_rounds
        self._memory_tools = memory_tools

    async def run(
        self,
        history: list[dict],
        user_input: str,
        *,
        workspace_id: int,
        user_id: int,
        db: Session,
        tool_trace: list[dict] | None = None,
    ) -> str:
        return await self._run_async(
            history=history,
            user_input=user_input,
            workspace_id=workspace_id,
            user_id=user_id,
            db=db,
            tool_trace=tool_trace,
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
        logger.info(
            "Agent run started: user_id=%s workspace_id=%s max_tool_rounds=%s",
            user_id,
            workspace_id,
            self._max_tool_rounds,
        )
        try:
            remote_clients, tool_allowlists = await asyncio.to_thread(
                prepare_mcp_clients,
                db,
                workspace_id,
                user_id,
            )

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

                    if self._memory_tools:
                        tools += self._memory_tools.get_openai_tools()

                    logger.info(
                        "LLM request started: step=%s messages=%s tools=%s",
                        step,
                        len(messages),
                        len(tools),
                    )
                    logger.info(
                        "LLM request messages:\n%s",
                        json.dumps(
                            messages,
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        ),
                    )

                    logger.info(
                        "LLM request tools:\n%s",
                        json.dumps(
                            tools,
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        ),
                    )
                    response = await asyncio.to_thread(
                        self._agent.generate,
                        messages=messages,
                        tools=tools,
                    )

                    self._record_llm_metrics(response)

                    choice = response.choices[0]
                    message = choice.message

                    finish_reason = choice.finish_reason
                    tool_calls = choice.message.tool_calls

                    logger.info(
                        "LLM response received: step=%s finish_reason=%s tool_calls=%s",
                        step,
                        finish_reason,
                        len(tool_calls or []),
                    )

                    if finish_reason == "stop":
                        run_status = "success"
                        return message.content or ""

                    if finish_reason == "length":
                        run_status = "incomplete"
                        return message.content or "LLM response was truncated."

                    if finish_reason == "content_filter":
                        run_status = "filtered"
                        return "Ответ заблокирован фильтром содержимого."

                    if finish_reason != "tool_calls":
                        raise RuntimeError(f"Unexpected finish reason: {finish_reason}")

                    if not tool_calls:
                        raise RuntimeError(
                            "LLM returned tool_calls finish_reason without tool calls"
                        )

                    try:
                        ai_message = self._build_ai_message(message)
                    except (json.JSONDecodeError, ValueError) as error:
                        logger.warning("Invalid tool call arguments: %s", error)
                        raise RuntimeError(
                            "LLM returned invalid tool call arguments"
                        ) from error

                    messages.append(ai_message)

                    for tool_call in ai_message.tool_calls:
                        call_id = tool_call["id"]

                        if call_id is None:
                            raise RuntimeError("LLM returned tool call without an ID")

                        tool_message = await self._execute_tool(
                            mcp=mcp,
                            name=tool_call["name"],
                            call_id=call_id,
                            arguments=tool_call["args"],
                            tool_trace=tool_trace,
                            user_id=user_id,
                        )
                        messages.append(tool_message)

                run_status = "max_tool_rounds"
                return "Не удалось завершить выполнение."

        except Exception:
            logger.exception(
                "Agent run failed: user_id=%s workspace_id=%s",
                user_id,
                workspace_id,
            )
            raise
        finally:
            AGENT_ACTIVE_RUNS.dec()
            AGENT_RUNS.labels(status=run_status).inc()
            AGENT_RUN_DURATION.observe(perf_counter() - started)

    @staticmethod
    def _record_llm_metrics(response) -> None:
        usage = response.usage

        if usage is not None:
            LLM_PROMPT_TOKENS.inc(usage.prompt_tokens)
            LLM_COMPLETION_TOKENS.inc(usage.completion_tokens)

        finish_reason = response.choices[0].finish_reason or "unknown"
        LLM_FINISH_REASONS.labels(reason=finish_reason).inc()
        logger.info(
            "LLM token usage: prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.total_tokens,
        )

    @staticmethod
    def _build_ai_message(message) -> AIMessage:
        tool_calls = []

        for call in message.tool_calls:
            arguments = json.loads(call.function.arguments or "{}")

            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Tool arguments must be a JSON object: {call.function.name}"
                )

            tool_calls.append(
                {
                    "name": call.function.name,
                    "args": arguments,
                    "id": call.id,
                    "type": "tool_call",
                }
            )

        return AIMessage(
            content=message.content or "",
            tool_calls=tool_calls,
        )

    async def _execute_tool(
        self,
        mcp: MCPManager,
        name: str,
        call_id: str,
        arguments: dict,
        tool_trace: list[dict] | None = None,
        user_id: int = 0,
    ) -> ToolMessage:

        metric_tool = name.split("__", maxsplit=1)[-1]
        started = perf_counter()
        status = "error"

        trace_entry = None
        if tool_trace is not None:
            trace_entry = {"name": name, "status": "running"}
            tool_trace.append(trace_entry)

        logger.info(
            "Tool execution started: name=%s call_id=%s",
            name,
            call_id,
        )
        try:
            if self._memory_tools and name.startswith("memory__"):
                content = await asyncio.to_thread(
                    self._memory_tools.execute,
                    name=name,
                    arguments=arguments,
                    user_id=user_id,
                )
            else:
                result = await mcp.call_tool(
                    name=name,
                    arguments=arguments,
                )
                content = str(result)

            status = "success"

        except Exception:
            logger.exception(
                "Tool execution failed: name=%s call_id=%s",
                name,
                call_id,
            )
            content = "Tool execution failed."

        finally:
            TOOL_CALLS.labels(
                tool=metric_tool,
                status=status,
            ).inc()

            TOOL_DURATION.observe(perf_counter() - started)

            if trace_entry is not None:
                trace_entry["status"] = status

            logger.info(
                "Tool execution finished: name=%s call_id=%s status=%s duration_ms=%.2f",
                name,
                call_id,
                status,
                (perf_counter() - started) * 1000,
            )

        return ToolMessage(
            content=content,
            tool_call_id=call_id,
        )
