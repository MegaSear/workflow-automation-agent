from react_agent.agent.http_client import _allowed_hosts

# Tool AllowList
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Получить текущее локальное время сервера. "
                "Вызывай, если пользователь просит узнать время "
                "или проверить работу инструмента."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": (
                "Проверить состояние Git-репозитория "
                "в изолированном контейнере. "
                "Не изменяет файлы."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Создать новый файл в изолированной рабочей области. Не перезаписывает существующие файлы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Выполнить HTTPS GET-запрос к публичному API. "
            f"Разрешённые хосты: {', '.join(sorted(_allowed_hosts()))}. "
            "Запросы только по HTTPS, без следования редиректам. "
            "Запросы к другим хостам отклоняются.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file inside the sandbox workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to /workspace.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_get_issue",
            "description": "Read a Jira issue by its key, e.g. PROJ-123.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                },
                "required": ["issue_key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_search_issues",
            "description": (
                "Search Jira issues using JQL. "
                "Read-only. Use max_results between 1 and 20."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "jql": {"type": "string"},
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["jql"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": (
                "List events in the user's primary Google Calendar. "
                "Dates must be ISO 8601 timestamps with a timezone. "
                "The range cannot exceed 31 days."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string"},
                    "time_max": {"type": "string"},
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["time_min", "time_max"],
                "additionalProperties": False,
            },
        },
    },
]
