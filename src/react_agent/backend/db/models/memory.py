from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from react_agent.backend.config import settings
from react_agent.backend.db.database import Base


class EpisodicMemory(Base):
    __tablename__ = "episodic_memories"

    __table_args__ = (
        Index(
            "ix_episodic_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={
                "m": settings.HNSW_M,
                "ef_construction": settings.HNSW_EF_CONSTRUCTION,
            },
            postgresql_ops={
                "embedding": "vector_cosine_ops",
            },
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.EPISODIC_MEMORY_EMBEDDING_DIMENSION),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
