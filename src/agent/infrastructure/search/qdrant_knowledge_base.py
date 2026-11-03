from pathlib import Path

from qdrant_client import QdrantClient, models

from agent.domain.knowledge import Chunk


class QdrantKnowledgeBase:
    """Implementa KnowledgeBase con Qdrant en modo local: una base vectorial embebida que vive en una carpeta, sin servidor."""

    # ponytail: el modo local compara contra todos los vectores y bloquea la carpeta mientras el cliente está abierto;
    # alcanza para miles de chunks por dominio. Con más volumen o varios procesos: Qdrant servidor o AI Search (S5)
    def __init__(self, path: Path, collection: str) -> None:
        self.path = path
        self.collection = collection

    def publish(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        client = QdrantClient(path=str(self.path))
        try:
            if not client.collection_exists(self.collection):
                size = len(chunks[0].content_vector)
                client.create_collection(self.collection, models.VectorParams(size=size, distance=models.Distance.COSINE))
            sources = sorted({chunk.source for chunk in chunks})
            by_fuente = models.Filter(must=[models.FieldCondition(key="source", match=models.MatchAny(any=sources))])
            client.delete(self.collection, points_selector=models.FilterSelector(filter=by_fuente))
            client.upsert(self.collection, points=[
                models.PointStruct(id=chunk.id, vector=chunk.content_vector, payload=chunk.model_dump(mode="json", exclude={"content_vector"}))
                for chunk in chunks
            ])
        finally:
            client.close()

    def count(self) -> int:
        client = QdrantClient(path=str(self.path))
        try:
            return client.count(self.collection).count if client.collection_exists(self.collection) else 0
        finally:
            client.close()