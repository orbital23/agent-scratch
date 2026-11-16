from fakes import RecordingChatModel

from agent.application.chat_service import ChatService
from agent.domain.models import Intent
from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore


def test_returns_typed_reply_with_system_prompt_first():
    model = RecordingChatModel()
    service = ChatService(
        model=model,
        store=InMemoryConversationStore(),
        system_prompt="SYS",
        max_turns=10,
    )
    reply = service.handle("s1", "Me robaron la tarjeta")
    assert reply.intent is Intent.SENSITIVE_ACTION
    assert [message["role"] for message in model.calls[0]] == ["system", "user"]
    assert model.calls[0][0]["content"] == "SYS"
