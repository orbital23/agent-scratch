"""Puertos: lo que el dominio necesita del mundo exterior. Las implementaciones viven en infrastructure."""

from typing import Protocol

from agent.domain.knowledge import Chunk
from agent.domain.models import Message, ModelResult


class ChatModel(Protocol):
    """Modelo de lenguaje. T1: Foundry directo; T3: Microsoft Agent Framework."""

    def complete(self, messages: list[Message]) -> ModelResult: ...


class ConversationStore(Protocol):
    """Historial por sesión. T1: memoria; T4: Cosmos DB."""

    def get(self, session_id: str) -> list[Message]: ...
    def append(self, session_id: str, message: Message) -> None: ...


class Embedder(Protocol):
    """Texto → vector. T2: Foundry text-embedding-3-small."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class KnowledgeBase(Protocol):
    """Índice de conocimiento. S3: Qdrant en modo local; S5: Azure AI Search."""

    def publish(self, chunks: list[Chunk]) -> None:
        """Reemplaza todos los chunks de cada fuente publicada."""
        ...

    def count(self) -> int: ...