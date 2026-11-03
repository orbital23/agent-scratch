from agent.application.chunker import chunk_document
from agent.domain.knowledge import Chunk, SourceDocument
from agent.domain.ports import Embedder


class IngestCorpus:
    """Caso de uso: documentos → chunks con su vector. Publicar es otro paso, para revisar antes qué se va a indexar."""

    def __init__(self, embedder: Embedder, chunk_max_chars: int, batch_size: int) -> None:
        self.embedder = embedder
        self.chunk_max_chars = chunk_max_chars
        self.batch_size = batch_size

    def build(self, documents: list[SourceDocument]) -> list[Chunk]:
        chunks = [chunk for document in documents for chunk in chunk_document(document, self.chunk_max_chars)]
        for start in range(0, len(chunks), self.batch_size):
            batch = chunks[start : start + self.batch_size]
            vectors = self.embedder.embed([chunk.content for chunk in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.content_vector = vector
        return chunks