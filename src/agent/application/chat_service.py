import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import jsonschema
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from agent.application.react_runtime import ReactRuntime
from agent.domain.errors import AgentError, ErrorKind
from agent.domain.knowledge import Citation, SearchHit
from agent.domain.models import (
    AgentTurn,
    Decision,
    Message,
    ModelResult,
    Skill,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolStatus,
    TurnEvent,
    Usage,
)
from agent.domain.ports import AgentRuntime, ChatModel, ConversationStore, Embedder, KnowledgeBase, QueryRewriter, Tools

log = logging.getLogger(__name__)
# S10: la API de OpenTelemetry es neutral (no sabe de Azure). Sin un exportador configurado, los spans no hacen nada.
tracer = trace.get_tracer(__name__)

MAX_TOOL_ROUNDS = 5  # criterio de terminación sin skill: sin esto, un modelo confundido pide tools para siempre
TOOL_MEMORY_CHARS = 600  # cuánto de cada resultado se recuerda en los turnos siguientes
TOOL_RETRIES = 1  # S8: una consulta que falla por conexión o timeout se reintenta una vez; una acción sensible, nunca
TOOL_RETRY_DELAY_S = 0.5
RETRYABLE = {ErrorKind.UPSTREAM, ErrorKind.TIMEOUT}  # fallas pasajeras del MCP; un error de negocio no mejora reintentando

REWRITE_PROMPT = (
    "Reescribe la última pregunta del cliente para que se entienda sola, sin leer la conversación. "
    "Conserva los productos, montos y fechas que se mencionaron antes. No la respondas."
)
CONTEXT_HEADER = (
    "Fragmentos del corpus para la última pregunta. Si es product_question, responde solo con ellos y pon en "
    "el campo sources los números que usaste; si no tienen la respuesta, dilo. No escribas los números dentro de la respuesta."
)
TOOLS_HEADER = (
    "Tienes tools del banco para consultar los datos del cliente y para pedir acciones. Para datos del cliente usa las "
    "tools: nunca inventes montos, fechas ni estados. Si ninguna tool sirve para lo que piden, dilo. Una acción sensible "
    "se pide con su tool solo cuando el cliente la pidió o la confirmó; entonces pídela sin volver a preguntar. Queda "
    "pendiente de aprobación de un asesor: díselo y no digas que ya se hizo. Solo una acción espera al asesor a la vez."
)
TOOL_MEMORY_HEADER = "Datos que devolvieron las tools en ese turno; si todavía sirven, úsalos sin volver a pedirlos:"
DECISION_HEADER = (
    "El asesor ya decidió la acción sensible que quedó pendiente. Con este resultado, dile al cliente en una o dos "
    "frases qué pasó, sin agregar nada que el resultado no diga: una solicitud registrada queda para que el banco la "
    "procese, no aplicada. No la vuelvas a pedir."
)
REJECTED = json.dumps({"status": "rechazada", "detail": "El asesor rechazó la acción: no se ejecutó."}, ensure_ascii=False)
ONE_PENDING = "Ya hay una acción esperando la decisión del asesor: no se pide otra hasta que la decida."
UNAVAILABLE = "El servicio del banco no respondió. Pide al cliente que lo intente más tarde."
UNCONFIRMED = (
    "El servicio del banco no respondió y no hay confirmación de que la acción se haya hecho. No la vuelvas a pedir: "
    "dile al cliente que un asesor la va a revisar."
)


@dataclass(frozen=True)
class PreparedTurn:
    """Lo que se arma antes de llamar al modelo: la pregunta, los mensajes con el contexto y lo que se encontró."""

    user: Message | None  # None cuando el turno lo abre la decisión del asesor, no un mensaje del cliente (S8)
    messages: list[Message]
    hits: list[SearchHit]
    rewrite_usage: Usage


class ChatService:
    """Caso de uso: resolver un turno de conversación con RAG y tools. Solo conoce puertos, nunca infraestructura."""

    def __init__(
        self,
        model: ChatModel,
        rewriter: QueryRewriter,
        embedder: Embedder,
        knowledge_base: KnowledgeBase,
        store: ConversationStore,
        system_prompt: str,
        max_turns: int,
        top_k: int,
        tools: Tools | None = None,  # sin tools (MCP_URL vacío), el agente responde solo con RAG
        skill: Skill | None = None,  # S7: la skill del dominio; sin ella, todas las tools de tu dominio y MAX_TOOL_ROUNDS
        runtime: AgentRuntime | None = None,  # S7: Agent Framework; por defecto, el ciclo ReAct propio sobre model
    ) -> None:
        self.rewriter = rewriter
        self.embedder = embedder
        self.knowledge_base = knowledge_base
        self.store = store
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.top_k = top_k
        self.tools = tools
        self.skill = skill
        self.runtime = runtime or ReactRuntime(model)
        self.tool_definitions = [
            tool for tool in (tools.definitions() if tools else []) if skill is None or tool.name in skill.tools
        ]
        self.max_tool_rounds = skill.max_tool_rounds if skill else MAX_TOOL_ROUNDS

    def handle(self, session_id: str, message: str) -> AgentTurn:
        *_, turn = self.handle_stream(session_id, message)
        return turn

    def handle_stream(self, session_id: str, message: str) -> Iterator[TurnEvent]:
        """Entrega la respuesta mientras el modelo la escribe; el último evento es el AgentTurn.

        Reescribir y buscar ocurren aquí mismo, antes de devolver los eventos: si fallan, el AgentError sale de inmediato
        y la API todavía puede responder con su código HTTP (502, 504, 429).

        S10: el turno entero es un span (chat.turn), hijo del pedido HTTP: lo que tardó, lo que gastó y si falló, aunque
        falle a mitad del streaming. No se hace current entre un evento y otro: cada evento puede salir desde otro hilo.
        """
        span = tracer.start_span("chat.turn", attributes={"session.id": session_id})
        try:
            with trace.use_span(span, record_exception=False, set_status_on_exception=False):
                prepared = self._prepare(session_id, message)  # la búsqueda queda dentro del turno
        except Exception as error:
            _failed(span, error)
            span.end()
            raise
        return _traced(span, self._answer(session_id, prepared, self.tool_definitions, self.max_tool_rounds, span))

    def resolve(self, session_id: str, action_id: str, decision: Decision) -> AgentTurn:
        """S8: el asesor aprueba o rechaza la acción sensible pendiente; el modelo le cuenta al cliente qué pasó."""
        attributes = {"session.id": session_id, "agent.decision": decision.value}
        with tracer.start_as_current_span(  # S10: la decisión es su propio span, como un turno
            "chat.decision", attributes=attributes, record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                turn = self._decide(session_id, action_id, decision, span)
            except Exception as error:
                _failed(span, error)
                raise
            _record(span, turn)
            return turn

    def _decide(self, session_id: str, action_id: str, decision: Decision, span: Span) -> AgentTurn:
        call = self.store.pending(session_id)
        if call is None or call.id != action_id:
            raise AgentError(ErrorKind.NOT_FOUND, f"no hay una acción pendiente {action_id} en esta sesión")
        self.store.set_pending(session_id, None)  # checkpoint: se decide una sola vez, aunque el pedido llegue dos veces
        if decision is Decision.APPROVE:
            # no se reintenta sola: podría hacerse dos veces
            result = _traced_tool(call, span, lambda: self._call(call, retries=0, unavailable=UNCONFIRMED))
        else:
            result = ToolResult(call=call, status=ToolStatus.REJECTED, content=REJECTED)
        # checkpoint: lo que pasó en el banco queda en la memoria antes de llamar al modelo, aunque el modelo falle después
        self.store.append(session_id, {"role": "system", "content": _tool_memory([result])})
        log.info("trayectoria %s: decisión del asesor → %s %s", session_id, call.name, result.status)

        recent = self.store.get(session_id)[-self.max_turns * 2 :]
        decided: Message = {"role": "system", "content": DECISION_HEADER}
        prepared = PreparedTurn(user=None, messages=[*self._system(), *recent, decided], hits=[], rewrite_usage=Usage())
        *_, turn = self._answer(session_id, prepared, tools=[], max_rounds=1, span=span)  # sin tools: solo cuenta lo que pasó
        return turn.model_copy(update={"tools": [result]})

    def _system(self) -> list[Message]:
        system: list[Message] = [{"role": "system", "content": self.system_prompt}]
        if self.tool_definitions:
            system.append({"role": "system", "content": TOOLS_HEADER})
        if self.skill:
            system.append({"role": "system", "content": self.skill.instructions})
        return system

    def _prepare(self, session_id: str, message: str) -> PreparedTurn:
        user: Message = {"role": "user", "content": message}
        recent = self.store.get(session_id)[-self.max_turns * 2 :]

        query, rewrite_usage = message, Usage()
        if recent:  # la primera pregunta ya se entiende sola: no se gasta una llamada en reescribirla
            rewritten = self.rewriter.rewrite([{"role": "system", "content": REWRITE_PROMPT}, *recent, user])
            query, rewrite_usage = rewritten.query, rewritten.usage
        hits = self.knowledge_base.search(query, self.embedder.embed([query])[0], self.top_k)

        context: Message = {"role": "system", "content": _context_message(hits)}
        messages = [*self._system(), *recent, context, user]
        return PreparedTurn(user=user, messages=messages, hits=hits, rewrite_usage=rewrite_usage)

    def _answer(
        self, session_id: str, prepared: PreparedTurn, tools: list[ToolDefinition], max_rounds: int, span: Span
    ) -> Iterator[TurnEvent]:
        used: list[ToolResult] = []
        waiting = self.store.pending(session_id)

        def run_tool(call: ToolCall) -> ToolResult:
            nonlocal waiting
            result = _traced_tool(call, span, lambda: self._run(call, tools, waiting))
            if result.status is ToolStatus.PENDING_APPROVAL:
                waiting = call
            return result

        for event in self.runtime.run(prepared.messages, tools, run_tool, max_rounds):
            match event:
                case ModelResult():
                    yield self._finish(session_id, prepared, event, used)
                    return
                case ToolResult():
                    used.append(event)
                    yield event
                case _:
                    yield event
        raise AgentError(ErrorKind.INVALID_OUTPUT, "el runtime terminó sin una respuesta del modelo")

    def _run(self, call: ToolCall, tools: list[ToolDefinition], waiting: ToolCall | None) -> ToolResult:
        """Las reglas de cada tool que pide el modelo, con cualquier runtime: que exista, sus argumentos y si es sensible."""
        definition = next((tool for tool in tools if tool.name == call.name), None)
        if definition is None or self.tools is None:  # una tool fuera de la skill tampoco existe para el modelo
            return _error(call, f"La tool {call.name} no existe.")
        if problem := _invalid_arguments(call.arguments, definition.parameters):  # input inválido: no llega al MCP
            return _error(call, f"Argumentos inválidos para {call.name}: {problem}. Corrígelos o pregúntale al cliente.")
        if definition.sensitive:  # S8: no se ejecuta; queda esperando al asesor
            if waiting is not None:
                return _error(call, ONE_PENDING)
            return ToolResult(call=call, status=ToolStatus.PENDING_APPROVAL, content=_pending(call))
        return self._call(call, retries=TOOL_RETRIES)

    def _call(self, call: ToolCall, retries: int, unavailable: str = UNAVAILABLE) -> ToolResult:
        """Ejecuta en el MCP. Una falla pasajera se reintenta; si sigue, el modelo se entera y el turno sigue."""
        assert self.tools is not None  # _run y resolve solo llegan aquí con tools
        for attempt in range(1, retries + 2):
            try:
                return self.tools.call(call)
            except AgentError as error:
                if error.kind not in RETRYABLE:
                    raise
                log.warning("tool %s falló (intento %d de %d): %s", call.name, attempt, retries + 1, error)
                if attempt <= retries:
                    time.sleep(TOOL_RETRY_DELAY_S)
        return _error(call, unavailable)

    def _finish(self, session_id: str, prepared: PreparedTurn, result: ModelResult, tools: list[ToolResult]) -> AgentTurn:
        # se guarda solo si el modelo terminó de responder: un error, aunque sea a mitad del streaming, no deja turnos
        # a medias. El contexto no se guarda: cada turno busca de nuevo, y el historial no crece con fragmentos viejos.
        # Los datos de las tools sí (memoria de trabajo): "pide la devolución de esa" necesita el FEE del turno anterior
        if prepared.user is not None:
            self.store.append(session_id, prepared.user)
        if tools:
            self.store.append(session_id, {"role": "system", "content": _tool_memory(tools)})
        self.store.append(session_id, {"role": "assistant", "content": result.reply.answer})
        # la acción sensible espera al asesor solo si el turno terminó: un turno cortado no deja nada pendiente
        pending = next((tool.call for tool in tools if tool.status is ToolStatus.PENDING_APPROVAL), None)
        if pending:
            self.store.set_pending(session_id, pending)
        if prepared.user is not None:  # el turno de la decisión del asesor ya dejó su trayectoria en resolve
            log.info("trayectoria %s: %s → respuesta %s", session_id, _trajectory(tools), result.reply.intent)
        return AgentTurn(
            reply=result.reply,
            usage=prepared.rewrite_usage + result.usage,
            citations=_citations_from(result.reply.sources, prepared.hits),
            tools=tools,
            pending_action=pending,
            hits=prepared.hits,
        )


def _traced(span: Span, events: Iterator[TurnEvent]) -> Iterator[TurnEvent]:
    """Cierra el span del turno cuando el turno termina, falla o el cliente corta el streaming."""
    try:
        for event in events:
            if isinstance(event, AgentTurn):
                _record(span, event)
            yield event
    except Exception as error:
        _failed(span, error)
        raise
    finally:
        span.end()


def _traced_tool(call: ToolCall, parent: Span, run: Callable[[], ToolResult]) -> ToolResult:
    """Un span por tool, hijo del turno aunque el runtime la llame desde otro hilo (Agent Framework usa su propio loop).

    Sin argumentos ni resultado en el span: pueden traer datos del cliente.
    """
    with tracer.start_as_current_span(f"tool {call.name}", context=trace.set_span_in_context(parent)) as span:
        result = run()
        span.set_attributes(
            {"gen_ai.tool.name": call.name, "gen_ai.tool.call.id": call.id, "agent.tool.status": result.status.value}
        )
        if result.status is ToolStatus.ERROR:
            span.set_status(Status(StatusCode.ERROR, "la tool respondió con error"))
        return result


def _record(span: Span, turn: AgentTurn) -> None:
    """Lo que se mira de cada turno en App Insights. Sin el texto de la conversación: solo medidas e identificadores."""
    span.set_attributes(
        {
            "agent.intent": turn.reply.intent.value,
            "gen_ai.usage.input_tokens": turn.usage.prompt_tokens,
            "gen_ai.usage.output_tokens": turn.usage.completion_tokens,
            "agent.llm_calls": turn.usage.llm_calls,
            "agent.latency_ms": turn.usage.latency_ms,
            "agent.models": ",".join(turn.usage.models),
            "agent.tools": " ".join(f"{tool.call.name}:{tool.status.value}" for tool in turn.tools),
            "agent.citations": len(turn.citations),
            "agent.pending_action": turn.pending_action.name if turn.pending_action else "",
        }
    )
    span.set_status(StatusCode.OK)


def _failed(span: Span, error: Exception) -> None:
    span.record_exception(error)
    span.set_status(Status(StatusCode.ERROR, str(error)[:200]))
    span.set_attribute("agent.error", error.kind.value if isinstance(error, AgentError) else type(error).__name__)


def _invalid_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    """Qué está mal en los argumentos, según el JSON Schema de la tool; None si cumplen."""
    try:
        jsonschema.validate(arguments, schema)
    except jsonschema.ValidationError as error:
        return error.message
    return None


def _error(call: ToolCall, detail: str) -> ToolResult:
    return ToolResult(call=call, status=ToolStatus.ERROR, content=json.dumps({"error": detail}, ensure_ascii=False))


def _pending(call: ToolCall) -> str:
    detail = ("Acción sensible: no se ejecutó ni se registró todavía. Dile al cliente que la pediste y que un asesor "
              "la va a revisar.")
    return json.dumps({"status": "pendiente_aprobacion", "action_id": call.id, "detail": detail}, ensure_ascii=False)


def _trajectory(results: list[ToolResult]) -> str:
    """Cada paso del turno en una línea del log: qué tool, en qué orden y cómo terminó."""
    return " → ".join(f"{result.call.name} {result.status}" for result in results) or "sin tools"


def _tool_memory(results: list[ToolResult]) -> str:
    # ponytail: recorta cada resultado; si un dominio necesita listas largas, resumirlas con el modelo
    lines = [
        f"- {result.call.name}({json.dumps(result.call.arguments, ensure_ascii=False)}) → {result.status}: "
        f"{result.content[:TOOL_MEMORY_CHARS]}"
        for result in results
    ]
    return "\n".join([TOOL_MEMORY_HEADER, *lines])


def _context_message(hits: list[SearchHit]) -> str:
    if not hits:
        return "No se encontraron fragmentos del corpus para esta pregunta."
    blocks = [f"[{number}] {hit.chunk.source}\n{hit.chunk.content}" for number, hit in enumerate(hits, start=1)]
    return "\n\n".join([CONTEXT_HEADER, *blocks])


def _citations_from(numbers: list[int], hits: list[SearchHit]) -> list[Citation]:
    # el modelo solo elige números; uno que no existe se descarta, así ninguna cita es inventada
    cited_chunks = [hits[number - 1].chunk for number in dict.fromkeys(numbers) if 1 <= number <= len(hits)]
    return [Citation(source=chunk.source, section=chunk.section, chunk_id=chunk.id) for chunk in cited_chunks]