import pytest
from fakes import (
    FailingChatModel,
    FakeEmbedder,
    FakeKnowledgeBase,
    FakeTools,
    FlakyTools,
    InterruptedChatModel,
    RecordingChatModel,
    ToolCallingChatModel,
)

from agent.application import chat_service
from agent.application.chat_service import DECISION_HEADER, MAX_TOOL_ROUNDS, TOOLS_HEADER, ChatService
from agent.application.react_runtime import ReactRuntime
from agent.domain.errors import AgentError, ErrorKind
from agent.domain.knowledge import Chunk, Citation
from agent.domain.models import (
    AgentTurn,
    AnswerDelta,
    Decision,
    Intent,
    IntentDetected,
    Skill,
    ToolCall,
    ToolResult,
    ToolStatus,
)
from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore

DEADLINES = Chunk(id="c1", content="Plazos\n\nSe responde en 15 días.", doc_type="regulation", section="Plazos", source="regulation.pdf")
CHANNELS = Chunk(id="c2", content="Canales\n\nApp y agencias.", doc_type="faq", section="Canales", source="channels.html")


FEES = ToolCall(id="call-1", name="get_charged_fees", arguments={"customer_id": "CUS-1001"})
REFUND = ToolCall(id="call-2", name="request_fee_refund", arguments={"fee_id": "FEE-4002", "reason": "cobro indebido"})


FEES_SKILL = Skill(name="fees", instructions="SKILL fees", tools=["get_charged_fees"], max_tool_rounds=2)


def make_service(model, max_turns: int = 10, chunks: list[Chunk] | None = None, tools=None, skill=None) -> ChatService:
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
        skill=skill,
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

    service.runtime = ReactRuntime(FailingChatModel(ErrorKind.UPSTREAM))
    with pytest.raises(AgentError):
        service.handle("s1", "¿sigues?")

    service.runtime = ReactRuntime(model)
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


def test_skill_decides_which_tools_the_model_sees_and_adds_its_instructions():
    model = ToolCallingChatModel(REFUND)
    tools = FakeTools()
    turn = make_service(model, tools=tools, skill=FEES_SKILL).handle("s1", "Devuélvanme la FEE-4002")

    assert [tool.name for tool in model.offered[0]] == ["get_charged_fees"]
    assert "SKILL fees" in [message["content"] for message in model.received[0]]
    # el modelo pidió una tool fuera de la skill: no se ejecuta, aunque el MCP sí la muestre
    assert turn.tools[0].status is ToolStatus.ERROR
    assert tools.executed == []


def test_skill_sets_how_many_tool_rounds_the_model_gets():
    model = ToolCallingChatModel(FEES, rounds=FEES_SKILL.max_tool_rounds)
    with pytest.raises(AgentError) as error:
        make_service(model, tools=FakeTools(), skill=FEES_SKILL).handle("s1", "¿Qué me cobraron? Soy CUS-1001")
    assert error.value.kind is ErrorKind.INVALID_OUTPUT
    assert len(model.received) == FEES_SKILL.max_tool_rounds


def test_tool_data_is_remembered_for_the_next_turn():
    model = ToolCallingChatModel(FEES)
    service = make_service(model, tools=FakeTools())
    service.handle("s1", "¿Qué comisiones me cobraron? Soy CUS-1001")
    service.handle("s1", "Pide la devolución de esa")

    next_turn = model.received[-1]
    assert roles(next_turn) == ["system", "system", "user", "system", "assistant", "system", "user"]
    memory = next_turn[3]["content"]
    assert 'get_charged_fees({"customer_id": "CUS-1001"}) → ok' in memory
    assert "FEE-4002" in memory


def test_turn_without_tools_leaves_no_tool_memory():
    model = RecordingChatModel()
    service = make_service(model, tools=FakeTools())
    service.handle("s1", "Hola")
    service.handle("s1", "Gracias")
    assert roles(model.calls[-1]) == ["system", "system", "user", "assistant", "system", "user"]


# S8: control humano. Una acción sensible espera al asesor; una consulta que falla se reintenta; un input inválido no sale.


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(chat_service, "TOOL_RETRY_DELAY_S", 0)


def test_a_sensitive_action_waits_for_the_advisor():
    tools = FakeTools()
    service = make_service(ToolCallingChatModel(REFUND), tools=tools)
    turn = service.handle("s1", "Devuélveme la comisión FEE-4002")

    assert tools.executed == []
    assert turn.pending_action == REFUND
    assert service.store.pending("s1") == REFUND
    assert REFUND.id in turn.tools[0].content  # el modelo sabe qué acción quedó esperando


def test_an_approved_action_runs_once_and_the_model_tells_the_customer():
    model, tools = ToolCallingChatModel(REFUND), FakeTools()
    service = make_service(model, tools=tools)
    service.handle("s1", "Devuélveme la comisión FEE-4002")
    turn = service.resolve("s1", REFUND.id, Decision.APPROVE)

    assert tools.executed == ["request_fee_refund"]
    assert turn.tools[0].status is ToolStatus.OK and turn.pending_action is None
    assert model.offered[-1] == []  # para contar lo que pasó, el modelo ya no puede pedir tools
    assert model.received[-1][-1] == {"role": "system", "content": DECISION_HEADER}
    with pytest.raises(AgentError) as error:  # la misma decisión dos veces no ejecuta la acción dos veces
        service.resolve("s1", REFUND.id, Decision.APPROVE)
    assert error.value.kind is ErrorKind.NOT_FOUND
    assert tools.executed == ["request_fee_refund"]


def test_a_rejected_action_is_not_executed_and_is_remembered():
    tools = FakeTools()
    service = make_service(ToolCallingChatModel(REFUND), tools=tools)
    service.handle("s1", "Devuélveme la comisión FEE-4002")
    turn = service.resolve("s1", REFUND.id, Decision.REJECT)

    assert tools.executed == []
    assert turn.tools[0].status is ToolStatus.REJECTED
    memory = service.store.get("s1")[-2]["content"]
    assert "request_fee_refund" in memory and "→ rejected" in memory
    assert service.store.pending("s1") is None


def test_a_decision_without_that_pending_action_is_not_found():
    service = make_service(ToolCallingChatModel(REFUND), tools=FakeTools())
    with pytest.raises(AgentError) as error:
        service.resolve("s1", REFUND.id, Decision.APPROVE)
    assert error.value.kind is ErrorKind.NOT_FOUND

    service.handle("s1", "Devuélveme la comisión FEE-4002")
    with pytest.raises(AgentError):
        service.resolve("s1", "call-otro", Decision.APPROVE)
    assert service.store.pending("s1") == REFUND  # un id equivocado no borra la que sí espera


def test_only_one_sensitive_action_waits_at_a_time():
    service = make_service(ToolCallingChatModel(REFUND), tools=FakeTools())
    earlier = ToolCall(id="call-0", name="request_fee_refund", arguments={"fee_id": "FEE-4001"})
    service.store.set_pending("s1", earlier)
    turn = service.handle("s1", "Devuélveme también la FEE-4002")

    assert turn.tools[0].status is ToolStatus.ERROR
    assert turn.pending_action is None
    assert service.store.pending("s1") == earlier


def test_a_cut_turn_leaves_no_pending_action():
    service = make_service(ToolCallingChatModel(REFUND, rounds=99), tools=FakeTools())
    with pytest.raises(AgentError):
        service.handle("s1", "Devuélveme la comisión FEE-4002")
    assert service.store.pending("s1") is None


def test_invalid_arguments_never_reach_the_mcp():
    tools = FakeTools()
    wrong = ToolCall(id="call-4", name="get_charged_fees", arguments={"customer_id": 1001})
    turn = make_service(ToolCallingChatModel(wrong), tools=tools).handle("s1", "¿Mis comisiones? Soy 1001")

    assert tools.executed == []
    assert turn.tools[0].status is ToolStatus.ERROR
    assert "Argumentos inválidos" in turn.tools[0].content


def test_a_query_that_fails_once_is_retried():
    tools = FlakyTools(failures=1)
    turn = make_service(ToolCallingChatModel(FEES), tools=tools).handle("s1", "¿Mis comisiones? Soy CUS-1001")

    assert tools.attempts == 2
    assert turn.tools[0].status is ToolStatus.OK


def test_a_query_that_keeps_failing_is_an_error_and_the_turn_goes_on():
    tools = FlakyTools(failures=5)
    turn = make_service(ToolCallingChatModel(FEES), tools=tools).handle("s1", "¿Mis comisiones? Soy CUS-1001")

    assert tools.attempts == 1 + chat_service.TOOL_RETRIES
    assert turn.tools[0].status is ToolStatus.ERROR
    assert "no respondió" in turn.tools[0].content


def test_an_approved_action_is_never_retried():
    tools = FlakyTools(failures=1)
    service = make_service(ToolCallingChatModel(REFUND), tools=tools)
    service.handle("s1", "Devuélveme la comisión FEE-4002")
    turn = service.resolve("s1", REFUND.id, Decision.APPROVE)

    assert tools.attempts == 1  # reintentar podría pedir la devolución dos veces
    assert turn.tools[0].status is ToolStatus.ERROR
    assert "no hay confirmación" in turn.tools[0].content  # el modelo no la vuelve a pedir