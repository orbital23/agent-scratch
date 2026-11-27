import pytest
from fakes import FakeEmbedder, FakeKnowledgeBase, FakeTools, InterruptedChatModel, ToolCallingChatModel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from agent.application.chat_service import ChatService
from agent.domain.errors import AgentError
from agent.domain.models import Decision, ToolCall
from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)  # once per process: the service's tracer is a proxy that resolves to this one

FEES = ToolCall(id="call-1", name="get_charged_fees", arguments={"customer_id": "CUS-1001"})
REFUND = ToolCall(id="call-2", name="request_fee_refund", arguments={"fee_id": "FEE-4002", "reason": "cobro indebido"})


@pytest.fixture(autouse=True)
def clean_spans():
    EXPORTER.clear()


def make_service(model, tools=None) -> ChatService:
    return ChatService(
        model=model,
        rewriter=model,
        embedder=FakeEmbedder(),
        knowledge_base=FakeKnowledgeBase(),
        store=InMemoryConversationStore(),
        system_prompt="SYS",
        max_turns=10,
        top_k=5,
        tools=tools,
    )


def spans() -> dict:
    return {span.name: span for span in EXPORTER.get_finished_spans()}


def test_each_turn_is_one_span_with_its_tokens_latency_and_intent():
    turn = make_service(ToolCallingChatModel(FEES), tools=FakeTools()).handle("s1", "¿Qué comisiones me cobraron?")

    span = spans()["chat.turn"]
    assert span.status.status_code is StatusCode.OK
    assert span.attributes["session.id"] == "s1"
    assert span.attributes["agent.intent"] == turn.reply.intent.value
    assert span.attributes["gen_ai.usage.input_tokens"] == turn.usage.prompt_tokens
    assert span.attributes["gen_ai.usage.output_tokens"] == turn.usage.completion_tokens
    assert span.attributes["agent.llm_calls"] == 2
    assert span.attributes["agent.latency_ms"] == turn.usage.latency_ms
    assert span.attributes["agent.tools"] == "get_charged_fees:ok"


def test_each_tool_call_is_a_child_span_of_its_turn():
    make_service(ToolCallingChatModel(FEES), tools=FakeTools()).handle("s1", "¿Qué comisiones me cobraron?")

    turn, tool = spans()["chat.turn"], spans()["tool get_charged_fees"]
    assert tool.parent.span_id == turn.context.span_id
    assert tool.attributes["gen_ai.tool.name"] == "get_charged_fees"
    assert tool.attributes["agent.tool.status"] == "ok"


def test_a_failed_turn_is_an_error_span():
    with pytest.raises(AgentError):
        list(make_service(InterruptedChatModel()).handle_stream("s1", "¿Cuál es el plazo?"))

    span = spans()["chat.turn"]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["agent.error"] == "upstream"
    assert any(event.name == "exception" for event in span.events)


def test_the_advisor_decision_is_its_own_span_with_the_action_inside():
    service = make_service(ToolCallingChatModel(REFUND), tools=FakeTools())
    service.handle("s1", "Devuélveme la comisión FEE-4002")
    assert spans()["chat.turn"].attributes["agent.pending_action"] == "request_fee_refund"
    EXPORTER.clear()

    service.resolve("s1", REFUND.id, Decision.APPROVE)

    decision, tool = spans()["chat.decision"], spans()["tool request_fee_refund"]
    assert decision.attributes["agent.decision"] == "approve"
    assert tool.parent.span_id == decision.context.span_id
    assert tool.attributes["agent.tool.status"] == "ok"


def test_a_decision_without_a_pending_action_is_an_error_span():
    with pytest.raises(AgentError):
        make_service(ToolCallingChatModel(REFUND), tools=FakeTools()).resolve("s1", "call-x", Decision.APPROVE)

    span = spans()["chat.decision"]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["agent.error"] == "not_found"
    assert [event.name for event in span.events] == ["exception"]  # una sola vez, no duplicada