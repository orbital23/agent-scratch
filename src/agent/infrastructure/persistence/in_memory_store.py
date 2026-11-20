from collections import defaultdict

from agent.domain.models import Message, ToolCall


class InMemoryConversationStore:
    """Implementa el puerto ConversationStore en memoria."""

    # ponytail: se pierde al reiniciar y no escala a varias réplicas; Cosmos DB en T4
    def __init__(self) -> None:
        self._sessions: defaultdict[str, list[Message]] = defaultdict(list)
        self._pending: dict[str, ToolCall] = {}

    def get(self, session_id: str) -> list[Message]:
        return list(self._sessions[session_id])

    def append(self, session_id: str, message: Message) -> None:
        self._sessions[session_id].append(message)

    def pending(self, session_id: str) -> ToolCall | None:
        return self._pending.get(session_id)

    def set_pending(self, session_id: str, call: ToolCall | None) -> None:
        if call is None:
            self._pending.pop(session_id, None)
        else:
            self._pending[session_id] = call