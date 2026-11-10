from datetime import date

from pydantic import BaseModel


class SourceDocument(BaseModel):
    """Documento del corpus convertido a Markdown, con la metadata de su manifest."""

    source: str
    doc_type: str
    product: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    markdown: str


class Chunk(BaseModel):
    """Unidad que se indexa. Es el mismo esquema que idx-team-NN en Azure AI Search."""

    id: str
    content: str
    content_vector: list[float] = []
    doc_type: str
    product: str | None = None
    section: str
    valid_from: date | None = None
    valid_until: date | None = None
    source: str