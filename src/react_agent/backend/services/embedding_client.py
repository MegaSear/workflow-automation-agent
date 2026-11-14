from openai import OpenAI
from sentence_transformers import SentenceTransformer

from react_agent.backend.config import settings


class EmbeddingClient:
    def __init__(self):
        self._provider = settings.EMBEDDING_PROVIDER
        self._dimension = settings.EPISODIC_MEMORY_EMBEDDING_DIMENSION

        self._local_model = None
        self._api_client = None

        if self._provider == "sentence_transformers":
            self._local_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )

            actual_dimension = self._local_model.get_embedding_dimension()

            if actual_dimension != self._dimension:
                raise ValueError(
                    f"Expected dimension {self._dimension}, got {actual_dimension}"
                )

        elif self._provider == "openai_compatible":
            if not settings.EMBEDDING_BASE_URL:
                raise ValueError("EMBEDDING_BASE_URL is required")

            self._api_client = OpenAI(
                api_key=settings.EMBEDDING_API_KEY or "EMPTY",
                base_url=settings.EMBEDDING_BASE_URL,
            )

        else:
            raise ValueError(f"Unsupported embedding provider: {self._provider}")

    def embed(self, text: str, input_type: str = "document") -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        if input_type == "query":
            prefix = settings.EMBEDDING_QUERY_PREFIX
        elif input_type == "document":
            prefix = settings.EMBEDDING_DOCUMENT_PREFIX
        else:
            raise ValueError(f"Unsupported input type: {input_type}")

        text = prefix + text

        if self._provider == "sentence_transformers":
            embedding = self._local_model.encode(
                text,
                normalize_embeddings=True,
            ).tolist()

        else:
            response = self._api_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text,
            )
            embedding = response.data[0].embedding

        if len(embedding) != self._dimension:
            raise ValueError(
                f"Expected dimension {self._dimension}, got {len(embedding)}"
            )

        return embedding
