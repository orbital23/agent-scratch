import json
from collections.abc import Iterator
from dataclasses import dataclass

from agent.application.react_runtime import ReactRuntime
from agent.domain.errors import AgentError, ErrorKind
from agent.domain.knowledge import Citation, SearchHit
from agent.domain.models import (
    AgentTurn,
    Message,
    ModelResult,
    Skill,
    ToolCall,
    ToolResult,
    ToolStatus,
    TurnEvent,
    Usage,
)
from agent.domain.ports import AgentRuntime, ChatModel, ConversationStore, Embedder, KnowledgeBase, QueryRewriter, Tools

MAX_TOOL_ROUNDS = 5  # criterio de terminación sin skill: sin esto, un modelo confundido pide tools para siempre
TOOL_MEMORY_CHARS = 600  # cuánto de cada resultado se recuerda en los turnos siguientes

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
TOOL_MEMORY_HEADER = "Datos que devolvieron las tools en ese turno; si todavía sirven, úsalos sin volver a pedirlos:"
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
        """
        prepared = self._prepare(session_id, message)
        return self._answer(session_id, prepared)

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
        if self.skill:
            system.append({"role": "system", "content": self.skill.instructions})
        messages = [*system, *recent, context, user]
        return PreparedTurn(user=user, messages=messages, hits=hits, rewrite_usage=rewrite_usage)

    def _answer(self, session_id: str, prepared: PreparedTurn) -> Iterator[TurnEvent]:
        used: list[ToolResult] = []
        for event in self.runtime.run(prepared.messages, self.tool_definitions, self._run, self.max_tool_rounds):
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

    def _run(self, call: ToolCall) -> ToolResult:
        definition = next((tool for tool in self.tool_definitions if tool.name == call.name), None)
        if definition is None or self.tools is None:  # una tool fuera de la skill tampoco existe para el modelo
            return ToolResult(call=call, status=ToolStatus.ERROR, content=f"La tool {call.name} no existe.")
        if definition.sensitive:  # S8: aquí entra la aprobación humana
            return ToolResult(call=call, status=ToolStatus.PENDING_APPROVAL, content=PENDING_APPROVAL)
        return self.tools.call(call)

    def _finish(self, session_id: str, prepared: PreparedTurn, result: ModelResult, tools: list[ToolResult]) -> AgentTurn:
        # se guarda solo si el modelo terminó de responder: un error, aunque sea a mitad del streaming, no deja turnos
        # a medias. El contexto no se guarda: cada turno busca de nuevo, y el historial no crece con fragmentos viejos.
        # Los datos de las tools sí (memoria de trabajo): "pide la devolución de esa" necesita el FEE del turno anterior
        self.store.append(session_id, prepared.user)
        if tools:
            self.store.append(session_id, {"role": "system", "content": _tool_memory(tools)})
        self.store.append(session_id, {"role": "assistant", "content": result.reply.answer})
        return AgentTurn(
            reply=result.reply,
            usage=prepared.rewrite_usage + result.usage,
            citations=_citations_from(result.reply.sources, prepared.hits),
            tools=tools,
            hits=prepared.hits,
        )


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