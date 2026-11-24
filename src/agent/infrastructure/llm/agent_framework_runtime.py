import asyncio
import logging
import queue
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from agent_framework import Agent, AgentResponse, FunctionTool
from agent_framework import Message as AgentMessage
from agent_framework.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import AgentReply, Message, ModelResult, RuntimeEvent, ToolCall, ToolDefinition, ToolResult, Usage
from agent.infrastructure.llm.credentials import Credential
from agent.infrastructure.llm.foundry_chat_model import ReplyStream

log = logging.getLogger(__name__)

DONE = object()


class AgentFrameworkRuntime:
    """Implementa AgentRuntime con Microsoft Agent Framework (S7): su ciclo de tools y su streaming, contra Foundry.

    Cada tool llega al Agent como una función que llama a run_tool: la aprobación de las acciones sensibles sigue en
    ChatService y la llamada al MCP en McpTools. Agent Framework solo conduce el turno.
    """

    def __init__(self, endpoint: str, credential: Credential, deployment: str, timeout_s: float, max_retries: int) -> None:
        self.client = OpenAIChatCompletionClient(
            model=deployment,
            async_client=AsyncOpenAI(
                base_url=f"{endpoint.rstrip('/')}/openai/v1/",
                api_key=_async_key(credential),
                timeout=timeout_s,
                max_retries=max_retries,
            ),
        )
        self.deployment = deployment
        # el agente es síncrono y uvicorn ya corre su event loop: Agent Framework usa uno propio, en un hilo, que vive
        # tanto como el runtime. Uno nuevo por turno no sirve: el cliente async de OpenAI queda atado al primer loop
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def run(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        run_tool: Callable[[ToolCall], ToolResult],
        max_rounds: int,
    ) -> Iterator[RuntimeEvent]:
        events: queue.Queue[Any] = queue.Queue()

        async def drive() -> None:
            try:
                async for event in self._events(messages, tools, run_tool, max_rounds, events.put):
                    events.put(event)
            except Exception as error:
                events.put(error)
            finally:
                events.put(DONE)

        asyncio.run_coroutine_threadsafe(drive(), self.loop)  # cada evento cruza por la cola apenas llega
        while (event := events.get()) is not DONE:
            if isinstance(event, Exception):
                raise _agent_error(event) from event
            yield event

    async def _events(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        run_tool: Callable[[ToolCall], ToolResult],
        max_rounds: int,
        emit: Callable[[RuntimeEvent], None],
    ) -> AsyncIterator[RuntimeEvent]:
        start = time.perf_counter()
        self.client.function_invocation_configuration["max_iterations"] = max_rounds  # criterio de terminación
        agent = Agent(self.client, tools=[_as_function(tool, run_tool, emit) for tool in tools])
        stream = agent.run(
            [AgentMessage(message["role"], [message["content"]]) for message in messages],
            stream=True,
            options={"response_format": AgentReply},
        )
        reply_stream, snapshot = ReplyStream(), ""
        async for update in stream:
            for content in update.contents:
                if content.type == "text" and content.text:
                    snapshot += content.text
                    for event in reply_stream.events(snapshot):
                        yield event
        response = await stream.get_final_response()
        if not isinstance(response.value, AgentReply):
            raise AgentError(ErrorKind.INVALID_OUTPUT, f"el modelo pidió tools {max_rounds} veces sin responder el contrato")
        yield ModelResult(reply=response.value, usage=self._usage(response, start))

    def _usage(self, response: AgentResponse[Any], start: float) -> Usage:
        tokens = response.usage_details or {}
        usage = Usage(
            models=[self.deployment],
            llm_calls=sum(message.role == "assistant" for message in response.messages) or 1,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=tokens.get("input_token_count") or 0,
            completion_tokens=tokens.get("output_token_count") or 0,
        )
        log.info("llm AgentFramework %s", usage.model_dump())
        return usage


def _as_function(
    tool: ToolDefinition, run_tool: Callable[[ToolCall], ToolResult], emit: Callable[[RuntimeEvent], None]
) -> FunctionTool:
    async def call(**arguments: Any) -> str:
        # ponytail: Agent Framework no le pasa el id de la llamada a la función; uno propio basta para los eventos
        request = ToolCall(id=f"call-{uuid.uuid4().hex[:8]}", name=tool.name, arguments=arguments)
        emit(request)
        result = await asyncio.to_thread(run_tool, request)  # run_tool es síncrono: en un hilo, el loop sigue libre
        emit(result)
        return result.content

    return FunctionTool(name=tool.name, description=tool.description, func=call, input_model=tool.parameters)


def _async_key(credential: Credential) -> Credential | Callable[[], Any]:
    """El cliente async de OpenAI espera un proveedor de token async; el de Entra ID de credentials.py es síncrono."""
    if isinstance(credential, str):
        return credential

    async def token() -> str:
        return await asyncio.to_thread(credential)

    return token


def _agent_error(error: Exception) -> AgentError:
    if isinstance(error, AgentError):
        return error
    return AgentError(ErrorKind.UPSTREAM, f"Agent Framework: {type(error).__name__}: {str(error)[:200]}")