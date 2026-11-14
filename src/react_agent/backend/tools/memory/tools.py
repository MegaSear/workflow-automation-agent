import json

from react_agent.backend.services.memory_service import MemoryService


class MemoryTools:
    def __init__(self, service: MemoryService):
        self._service = service

    def get_openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "memory__add",
                    "description": "Save an important event or fact to episodic memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                        },
                        "required": ["content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory__search",
                    "description": "Search episodic memory for relevant information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer", "default": 5},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory__delete",
                    "description": "Delete an episodic memory entry by ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_id": {"type": "integer"},
                        },
                        "required": ["memory_id"],
                    },
                },
            },
        ]

    def execute(
        self,
        name: str,
        arguments: dict,
        user_id: int,
        conversation_id: int | None = None,
    ) -> str:
        if name == "memory__add":
            result = self._service.add(
                user_id=user_id,
                content=arguments["content"],
                conversation_id=conversation_id,
            )
        elif name == "memory__search":
            result = self._service.search(
                user_id=user_id,
                query=arguments["query"],
                limit=arguments.get("limit", 5),
            )
        elif name == "memory__delete":
            result = self._service.delete(
                user_id=user_id,
                memory_id=arguments["memory_id"],
            )
        else:
            raise ValueError(f"Unknown memory tool: {name}")

        return json.dumps(result, ensure_ascii=False, default=str)
