import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.knowledge import Citation, SearchHit
from agent.domain.models import (
    AgentTurn,
    Message,
    ModelEvent,
    ModelResult,
    ToolCall,
    ToolRequest,
    ToolResult,
    ToolStatus,
    TurnEvent,
    Usage,
)
from agent.domain.ports import ChatModel, ConversationStore, Embedder, KnowledgeBase, QueryRewriter, Tools

MAX_TOOL_ROUNDS = 5  # criterio de terminación: sin esto, un modelo confundido pide tools para siempre

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
    "pendiente de aprobación de un asesor: díselo y no digas que ya se hizo."
)
PENDING_APPROVAL = json.dumps(
    {"status": "pendiente_aprobacion",
     "detail": "Acción sensible: no se ejecutó ni se registró todavía. Dile al cliente que la pediste y que un asesor "
               "la va a revisar."},
    ensure_ascii=False,
)


@dataclass(frozen=True)
class PreparedTurn:
    """Lo que se arma antes de llamar al modelo: la pregunta, los mensajes con el contexto y lo que se encontró."""

    user: Message
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
    ) -> None:
        self.model = model
        self.rewriter = rewriter
        self.embedder = embedder
        self.knowledge_base = knowledge_base
        self.store = store
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.top_k = top_k
        self.tools = tools
        self.tool_definitions = tools.definitions() if tools else []

    def handle(self, session_id: str, message: str) -> AgentTurn:
        prepared = self._prepare(session_id, message)
        *_, turn = self._answer(session_id, prepared, lambda messages: [self.model.complete(messages, self.tool_definitions)])
        return turn

    def handle_stream(self, session_id: str, message: str) -> Iterator[TurnEvent]:
        """Igual que handle, pero entrega la respuesta mientras el modelo la escribe.

        Reescribir y buscar ocurren aquí mismo, antes de devolver los eventos: si fallan, el AgentError sale de inmediato
        y la API todavía puede responder con su código HTTP (502, 504, 429).
        """
        prepared = self._prepare(session_id, message)
        return self._answer(session_id, prepared, lambda messages: self.model.stream(messages, self.tool_definitions))

    def _prepare(self, session_id: str, message: str) -> PreparedTurn:
        user: Message = {"role": "user", "content": message}
        recent = self.store.get(session_id)[-self.max_turns * 2 :]

        query, rewrite_usage = message, Usage()
        if recent:  # la primera pregunta ya se entiende sola: no se gasta una llamada en reescribirla
            rewritten = self.rewriter.rewrite([{"role": "system", "content": REWRITE_PROMPT}, *recent, user])
            query, rewrite_usage = rewritten.query, rewritten.usage
        hits = self.knowledge_base.search(query, self.embedder.embed([query])[0], self.top_k)

        context: Message = {"role": "system", "content": _context_message(hits)}
        system: list[Message] = [{"role": "system", "content": self.system_prompt}]
        if self.tool_definitions:
            system.append({"role": "system", "content": TOOLS_HEADER})
        messages = [*system, *recent, context, user]
        return PreparedTurn(user=user, messages=messages, hits=hits, rewrite_usage=rewrite_usage)

    def _answer(
        self, session_id: str, prepared: PreparedTurn, ask: Callable[[list[Message]], Iterable[ModelEvent]]
    ) -> Iterator[TurnEvent]:
        """El ciclo ReAct: el modelo pide tools, el agente las ejecuta y le devuelve lo que pasó, hasta que responde."""
        messages, usage, used = list(prepared.messages), prepared.rewrite_usage, []
        for _ in range(MAX_TOOL_ROUNDS):
            for event in ask(messages):
                match event:
                    case ModelResult():
                        yield self._finish(session_id, prepared, event, usage, used)
                        return
                    case ToolRequest(calls=calls):
                        usage += event.usage
                    case _:
                        yield event
            messages.append(_assistant_asking(calls))
            for call in calls:
                yield call
                result = self._run(call)
                used.append(result)
                yield result
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result.content})
        raise AgentError(ErrorKind.INVALID_OUTPUT, f"el modelo pidió tools {MAX_TOOL_ROUNDS} veces seguidas sin responder")

    def _run(self, call: ToolCall) -> ToolResult:
        definition = next((tool for tool in self.tool_definitions if tool.name == call.name), None)
        if definition is None or self.tools is None:
            return ToolResult(call=call, status=ToolStatus.ERROR, content=f"La tool {call.name} no existe.")
        if definition.sensitive:  # S8: aquí entra la aprobación humana
            return ToolResult(call=call, status=ToolStatus.PENDING_APPROVAL, content=PENDING_APPROVAL)
        return self.tools.call(call)

    def _finish(
        self, session_id: str, prepared: PreparedTurn, result: ModelResult, usage: Usage, tools: list[ToolResult]
    ) -> AgentTurn:
        # se guarda solo si el modelo terminó de responder: un error, aunque sea a mitad del streaming, no deja turnos
        # a medias. El contexto no se guarda: cada turno busca de nuevo, y el historial no crece con fragmentos viejos
        self.store.append(session_id, prepared.user)
        self.store.append(session_id, {"role": "assistant", "content": result.reply.answer})
        return AgentTurn(
            reply=result.reply,
            usage=usage + result.usage,
            citations=_citations_from(result.reply.sources, prepared.hits),
            tools=tools,
            hits=prepared.hits,
        )


def _assistant_asking(calls: list[ToolCall]) -> Message:
    """El pedido del modelo, en los mensajes del turno: para entender cada resultado, el modelo necesita ver qué pidió."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call.id, "type": "function",
             "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}}
            for call in calls
        ],
    }


def _context_message(hits: list[SearchHit]) -> str:
    if not hits:
        return "No se encontraron fragmentos del corpus para esta pregunta."
    blocks = [f"[{number}] {hit.chunk.source}\n{hit.chunk.content}" for number, hit in enumerate(hits, start=1)]
    return "\n\n".join([CONTEXT_HEADER, *blocks])


def _citations_from(numbers: list[int], hits: list[SearchHit]) -> list[Citation]:
    # el modelo solo elige números; uno que no existe se descarta, así ninguna cita es inventada
    cited_chunks = [hits[number - 1].chunk for number in dict.fromkeys(numbers) if 1 <= number <= len(hits)]
    return [Citation(source=chunk.source, section=chunk.section, chunk_id=chunk.id) for chunk in cited_chunks]