import pytest
from fakes import (
    FailingChatModel,
    FakeEmbedder,
    FakeKnowledgeBase,
    FakeTools,
    InterruptedChatModel,
    RecordingChatModel,
    ToolCallingChatModel,
)

from agent.application.chat_service import MAX_TOOL_ROUNDS, TOOLS_HEADER, ChatService
from agent.domain.errors import AgentError, ErrorKind
from agent.domain.knowledge import Chunk, Citation
from agent.domain.models import AgentTurn, AnswerDelta, Intent, IntentDetected, ToolCall, ToolResult, ToolStatus
from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore

DEADLINES = Chunk(id="c1", content="Plazos\n\nSe responde en 15 días.", doc_type="regulation", section="Plazos", source="regulation.pdf")
CHANNELS = Chunk(id="c2", content="Canales\n\nApp y agencias.", doc_type="faq", section="Canales", source="channels.html")


FEES = ToolCall(id="call-1", name="get_charged_fees", arguments={"customer_id": "CUS-1001"})
REFUND = ToolCall(id="call-2", name="request_fee_refund", arguments={"fee_id": "FEE-4002", "reason": "cobro indebido"})


def make_service(model, max_turns: int = 10, chunks: list[Chunk] | None = None, tools=None) -> ChatService:
    return ChatService(
        model=model,
        rewriter=model,
        embedder=FakeEmbedder(),
        knowledge_base=FakeKnowledgeBase(chunks),
        store=InMemoryConversationStore(),
        system_prompt="SYS",
        max_turns=max_turns,
        top_k=5,
        tools=tools,
    )


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

    assert roles(model.calls[1]) == ["system", "user", "assistant", "system", "user"]
    assert model.calls[1][0]["content"] == "SYS"
    assert model.calls[1][1]["content"] == "Hola"


def test_sessions_are_isolated():
    model = RecordingChatModel()
    service = make_service(model)

    service.handle("s1", "Hola")
    service.handle("s2", "Hola")

    assert roles(model.calls[1]) == ["system", "system", "user"]


def test_history_is_trimmed_to_max_turns():
    model = RecordingChatModel()
    service = make_service(model, max_turns=1)

    for text in ("uno", "dos", "tres"):
        service.handle("s1", text)

    assert [message["content"] for message in model.calls[2][1:-2]] == ["dos", "[fake] intención detectada: out_of_scope"]


def test_failed_turn_is_not_saved():
    model = RecordingChatModel()
    service = make_service(model)
    service.handle("s1", "Hola")

    service.model = FailingChatModel(ErrorKind.UPSTREAM)
    with pytest.raises(AgentError):
        service.handle("s1", "¿sigues?")

    service.model = model
    service.handle("s1", "Me robaron la tarjeta")
    assert roles(model.calls[-1]) == ["system", "user", "assistant", "system", "user"]


def test_context_numbers_the_chunks_found():
    model = RecordingChatModel()
    make_service(model, chunks=[DEADLINES, CHANNELS]).handle("s1", "¿Cuál es el plazo?")

    context = model.calls[0][-2]["content"]
    assert "[1] regulation.pdf\nPlazos" in context
    assert "[2] channels.html\nCanales" in context


def test_without_chunks_the_model_is_told_there_is_no_context():
    model = RecordingChatModel()
    make_service(model).handle("s1", "¿Cuál es el plazo?")
    assert model.calls[0][-2]["content"].startswith("No se encontraron fragmentos")


def test_citations_come_only_from_fragments_that_exist():
    model = RecordingChatModel(sources=[2, 7, 2])
    turn = make_service(model, chunks=[DEADLINES, CHANNELS]).handle("s1", "¿Por dónde reclamo?")
    assert turn.citations == [Citation(source="channels.html", section="Canales", chunk_id="c2")]


def test_follow_up_question_is_rewritten_before_searching():
    model = RecordingChatModel()
    service = make_service(model)

    service.handle("s1", "¿Cuál es el plazo de un reclamo?")
    turn = service.handle("s1", "¿y si es fraude?")

    assert service.knowledge_base.queries == ["¿Cuál es el plazo de un reclamo?", "[reescrita] ¿y si es fraude?"]
    assert roles(model.rewrites[0]) == ["system", "user", "assistant", "user"]
    assert turn.usage.llm_calls == 2


def test_stream_sends_the_intent_then_the_answer_in_pieces_then_the_turn():
    service = make_service(RecordingChatModel(sources=[1]), chunks=[DEADLINES])

    events = list(service.handle_stream("s1", "¿Cuál es el plazo?"))

    assert events[0] == IntentDetected(intent=Intent.PRODUCT_QUESTION)
    assert all(isinstance(event, AnswerDelta) for event in events[1:-1])
    turn = events[-1]
    assert isinstance(turn, AgentTurn)
    assert "".join(event.text for event in events[1:-1]).strip() == turn.reply.answer
    assert turn.citations == [Citation(source="regulation.pdf", section="Plazos", chunk_id="c1")]
    assert roles(service.store.get("s1")) == ["user", "assistant"]


def test_stream_cut_in_the_middle_does_not_save_the_turn():
    service = make_service(InterruptedChatModel())

    with pytest.raises(AgentError):
        list(service.handle_stream("s1", "¿Cuál es el plazo?"))

    assert service.store.get("s1") == []


def test_the_model_asks_a_tool_and_answers_with_its_result():
    model, tools = ToolCallingChatModel(FEES), FakeTools()
    turn = make_service(model, tools=tools).handle("s1", "¿Qué comisiones me cobraron? Soy CUS-1001")

    assert tools.executed == ["get_charged_fees"]
    assert turn.tools == [ToolResult(call=FEES, status=ToolStatus.OK, content='{"result": [{"id": "FEE-4002", "refundable": true}]}')]
    assert "FEE-4002" in turn.reply.answer
    assert turn.usage.llm_calls == 2  # la vuelta que pidió la tool y la que respondió
    first, second = model.received
    assert {"role": "system", "content": TOOLS_HEADER} in first
    assert roles(second)[-2:] == ["assistant", "tool"]  # el pedido del modelo y lo que respondió la tool
    assert second[-2]["tool_calls"][0]["function"]["name"] == "get_charged_fees"


def test_sensitive_actions_are_not_executed():
    tools = FakeTools()
    turn = make_service(ToolCallingChatModel(REFUND), tools=tools).handle("s1", "Devuélveme la comisión FEE-4002")

    assert tools.executed == []
    assert turn.tools[0].status == ToolStatus.PENDING_APPROVAL
    assert "pendiente_aprobacion" in turn.tools[0].content


def test_a_tool_that_does_not_exist_is_an_error_for_the_model():
    tools = FakeTools()
    unknown = ToolCall(id="call-3", name="delete_customer", arguments={})
    turn = make_service(ToolCallingChatModel(unknown), tools=tools).handle("s1", "Borra mis datos")

    assert tools.executed == []
    assert turn.tools[0].status == ToolStatus.ERROR


def test_without_tools_the_model_gets_no_tools_header():
    model = RecordingChatModel()
    make_service(model).handle("s1", "¿Cuál es el plazo?")
    assert {"role": "system", "content": TOOLS_HEADER} not in model.calls[0]


def test_stream_shows_each_tool_before_the_answer():
    events = list(make_service(ToolCallingChatModel(FEES), tools=FakeTools()).handle_stream("s1", "¿Mis comisiones?"))

    assert [type(event) for event in events[:3]] == [ToolCall, ToolResult, IntentDetected]
    assert isinstance(events[3], AnswerDelta)
    assert isinstance(events[-1], AgentTurn) and events[-1].tools[0].call == FEES


def test_a_model_that_never_stops_asking_for_tools_is_cut():
    model = ToolCallingChatModel(FEES, rounds=99)
    service = make_service(model, tools=FakeTools())
    with pytest.raises(AgentError) as error:
        service.handle("s1", "¿Mis comisiones?")
    assert error.value.kind == ErrorKind.INVALID_OUTPUT
    assert len(model.received) == MAX_TOOL_ROUNDS
    assert service.store.get("s1") == []  # un turno cortado no se guarda