from datetime import date

from agent.domain.knowledge import Chunk
from agent.infrastructure.search.azure_search_knowledge_base import (
    AzureSearchKnowledgeBase,
    from_document,
    still_valid_filter,
)


class FakeSearchClient:
    """La parte de SearchClient que usa publish, con el índice en un dict."""

    def __init__(self, ids: list[str]) -> None:
        self.documents = {id: {"id": id} for id in ids}
        self.deleted: list[str] = []

    def get_document_count(self) -> int:
        return len(self.documents)

    def search(self, search_text, filter, select):
        return list(self.documents.values())

    def upload_documents(self, documents):
        self.documents |= {document["id"]: document for document in documents}

    def delete_documents(self, documents):
        for document in documents:
            self.deleted.append(document["id"])
            del self.documents[document["id"]]


def chunk(id: str, valid_until: date | None = None) -> Chunk:
    return Chunk(id=id, content="x", content_vector=[0.1], doc_type="faq", section="FAQ", source="a.md",
                 valid_until=valid_until)


def test_publish_writes_index_documents_and_deletes_only_the_stale_ones():
    base = AzureSearchKnowledgeBase.__new__(AzureSearchKnowledgeBase)
    base.client = FakeSearchClient(["c1", "old"])
    expired = chunk("c1", valid_until=date(2024, 12, 31))

    base.publish([expired, chunk("c2")])

    document = base.client.documents["c1"]
    assert document["valid_until"] == "2024-12-31T00:00:00Z"
    assert document["valid_from"] is None
    assert from_document({**document, "@search.score": 1.0}) == expired.model_copy(update={"content_vector": []})
    assert base.client.deleted == ["old"]
    assert base.count() == 2
    assert still_valid_filter(date(2026, 10, 23)) == "valid_until eq null or valid_until ge 2026-10-23T00:00:00Z"