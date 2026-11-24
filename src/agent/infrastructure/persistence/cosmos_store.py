from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from azure.cosmos import ContainerProxy
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import Message, ToolCall


class CosmosConversationStore:
    """Implements ConversationStore on the team's Cosmos DB container: sessions survive restarts and deployments.

    One document per session: {id, userId, messages, pending}. The container is partitioned by /userId and the agent has
    no users, so the session id is also the partition.
    """

    # ponytail: each write rewrites the whole document (last write wins, 2 MB per item); patch_item if sessions grow
    def __init__(self, container: ContainerProxy) -> None:
        self.container = container

    def get(self, session_id: str) -> list[Message]:
        return self._read(session_id)["messages"]

    def append(self, session_id: str, message: Message) -> None:
        document = self._read(session_id)
        document["messages"].append(message)
        self._write(document)

    def pending(self, session_id: str) -> ToolCall | None:
        pending = self._read(session_id)["pending"]
        return ToolCall.model_validate(pending) if pending else None

    def set_pending(self, session_id: str, call: ToolCall | None) -> None:
        document = self._read(session_id)
        document["pending"] = call.model_dump() if call else None
        self._write(document)

    def _read(self, session_id: str) -> dict[str, Any]:
        with _cosmos_errors():
            try:
                return self.container.read_item(item=session_id, partition_key=session_id)
            except CosmosResourceNotFoundError:
                return {"id": session_id, "userId": session_id, "messages": [], "pending": None}

    def _write(self, document: dict[str, Any]) -> None:
        with _cosmos_errors():
            self.container.upsert_item(body=document)


@contextmanager
def _cosmos_errors() -> Iterator[None]:
    try:
        yield
    except CosmosHttpResponseError as error:
        raise AgentError(ErrorKind.UPSTREAM, f"error de Cosmos DB: HTTP {error.status_code}") from error