from agent.domain.knowledge import Chunk
from agent.infrastructure.search.qdrant_knowledge_base import QdrantKnowledgeBase


def chunk(chunk_id: str, source: str, vector: list[float]) -> Chunk:
    return Chunk(id=chunk_id, content="texto", content_vector=vector, doc_type="faq", section="FAQ", source=source)


A1, A2, A3, B1 = (f"00000000-0000-0000-0000-00000000000{number}" for number in range(1, 5))


def test_publish_replaces_the_chunks_of_each_source(tmp_path):
    index = QdrantKnowledgeBase(tmp_path / "fraud", collection="fraud")
    index.publish([chunk(A1, "a.md", [1, 0]), chunk(A2, "a.md", [0, 1]), chunk(B1, "b.md", [1, 1])])

    index.publish([chunk(A3, "a.md", [1, 0])])

    assert QdrantKnowledgeBase(tmp_path / "fraud", collection="fraud").count() == 2


def test_count_is_zero_before_publishing(tmp_path):
    assert QdrantKnowledgeBase(tmp_path / "fraud", collection="fraud").count() == 0