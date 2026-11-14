from sqlalchemy import func, select

from react_agent.backend.config import settings
from react_agent.backend.db.models.memory import EpisodicMemory
from react_agent.backend.services.embedding_client import EmbeddingClient


class MemoryService:
    def __init__(self, session_factory, embedding_client: EmbeddingClient):
        self._session_factory = session_factory
        self._embedding_client = embedding_client

    def add(
        self,
        user_id: int,
        content: str,
        conversation_id: int | None = None,
    ) -> int:
        embedding = self._embedding_client.embed(
            content,
            input_type="document",
        )
        with self._session_factory() as session:
            with session.begin():
                memory = EpisodicMemory(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    content=content,
                    embedding=embedding,
                )
                session.add(memory)
                session.flush()
                memory_id = memory.id

        return memory_id

    def search(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")

        embedding = self._embedding_client.embed(
            query,
            input_type="query",
        )
        with self._session_factory() as session:
            with session.begin():
                session.execute(
                    select(
                        func.set_config(
                            "hnsw.ef_search",
                            str(settings.HNSW_EF_SEARCH),
                            True,
                        )
                    )
                )

                distance = EpisodicMemory.embedding.cosine_distance(embedding)

                statement = (
                    select(EpisodicMemory, distance.label("distance"))
                    .where(EpisodicMemory.user_id == user_id)
                    .order_by(distance)
                    .limit(limit)
                )

                rows = session.execute(statement).all()

                return [
                    {
                        "id": memory.id,
                        "content": memory.content,
                        "created_at": memory.created_at,
                        "distance": distance,
                    }
                    for memory, distance in rows
                ]

    def delete(self, user_id: int, memory_id: int) -> bool:
        with self._session_factory() as session:
            with session.begin():
                statement = select(EpisodicMemory).where(
                    EpisodicMemory.id == memory_id,
                    EpisodicMemory.user_id == user_id,
                )
                memory = session.scalar(statement)

                if memory is None:
                    return False

                session.delete(memory)

        return True
