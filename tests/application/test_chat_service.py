import pytest
from fakes import FailingChatModel, RecordingChatModel

from agent.application.chat_service import ChatService
from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import Intent
from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore


def make_service(model, max_turns: int = 10) -> ChatService:
    return ChatService(model=model, store=InMemoryConversationStore(), system_prompt="SYS", max_turns=max_turns)


def roles(messages) -> list[str]:
    return [message["role"] for message in messages]


def test_returns_typed_turn():
    turn = make_service(RecordingChatModel()).handle("s1", "Me robaron la tarjeta")
    assert turn.reply.intent is Intent.SENSITIVE_ACTION
    assert turn.usage.llm_calls == 1


def test_history_is_sent_on_next_turn():
    model = RecordingChatModel()
    service = make_service(model)

    service.handle("s1", "Hola")
    service.handle("s1", "Me robaron la tarjeta")

    assert roles(model.calls[1]) == ["system", "user", "assistant", "user"]
    assert model.calls[1][0]["content"] == "SYS"
    assert model.calls[1][1]["content"] == "Hola"


def test_sessions_are_isolated():
    model = RecordingChatModel()
    service = make_service(model)

    service.handle("s1", "Hola")
    service.handle("s2", "Hola")

    assert roles(model.calls[1]) == ["system", "user"]


def test_history_is_trimmed_to_max_turns():
    model = RecordingChatModel()
    service = make_service(model, max_turns=1)

    for text in ("uno", "dos", "tres"):
        service.handle("s1", text)

    assert [message["content"] for message in model.calls[2][1:-1]] == ["dos", "[fake] intención detectada: out_of_scope"]


def test_failed_turn_is_not_saved():
    model = RecordingChatModel()
    service = make_service(model)
    service.handle("s1", "Hola")

    service.model = FailingChatModel(ErrorKind.UPSTREAM)
    with pytest.raises(AgentError):
        service.handle("s1", "¿sigues?")

    service.model = model
    service.handle("s1", "Me robaron la tarjeta")
    assert roles(model.calls[-1]) == ["system", "user", "assistant", "user"]