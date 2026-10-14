
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
