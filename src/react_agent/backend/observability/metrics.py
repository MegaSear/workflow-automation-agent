from prometheus_client import Counter, Gauge, Histogram

# Количество завершённых запусков агента.
AGENT_RUNS = Counter(
    "agent_runs_total",
    "Number of agent runs",
    ["status"],
)

# Время выполнения всей задачи в секундах.
AGENT_RUN_DURATION = Histogram(
    "agent_run_duration_seconds",
    "Duration of agent runs",
)

# Количество задач, выполняющихся прямо сейчас.
AGENT_ACTIVE_RUNS = Gauge(
    "agent_active_runs",
    "Number of active agent runs",
)

# Количество вызовов инструментов.
TOOL_CALLS = Counter(
    "agent_tool_calls_total",
    "Number of tool calls",
    ["tool", "status"],
)

# Время выполнения каждого инструмента.
TOOL_DURATION = Histogram(
    "agent_tool_duration_seconds",
    "Duration of tool calls",
)

LLM_PROMPT_TOKENS = Counter(
    "llm_prompt_tokens_total",
    "Total prompt tokens consumed",
)

LLM_COMPLETION_TOKENS = Counter(
    "llm_completion_tokens_total",
    "Total completion tokens generated",
)

LLM_FINISH_REASONS = Counter(
    "llm_finish_reasons_total",
    "Number of LLM responses by finish reason",
    ["reason"],
)
