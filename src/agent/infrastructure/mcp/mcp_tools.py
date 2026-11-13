import asyncio
import json
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from mcp.types import Tool

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import ToolCall, ToolDefinition, ToolResult, ToolStatus

DOMAIN_HEADER = "X-Bank-Domain"

TokenProvider = Callable[[], str]  # devuelve un token de Entra vigente; lo renueva solo


def mcp_client(server: str | FastMCP, domain: str = "", token: TokenProvider | None = None) -> Client:
    """Por HTTP, el header X-Bank-Domain le dice al MCP el dominio del agente: solo ve sus tools. En memoria, todas.

    Con token (el MCP compartido), cada conexión manda un Bearer recién pedido. Sin token (el mock), no manda ninguno.
    """
    if isinstance(server, str):
        headers = {DOMAIN_HEADER: domain} if domain else {}
        if token:
            headers["Authorization"] = f"Bearer {token()}"
        return Client(StreamableHttpTransport(server, headers=headers or None))
    return Client(server)


class McpTools:
    """Implementa Tools con un servidor MCP: el mock local o el compartido, según MCP_URL. DOMAIN decide qué tools ve."""

    def __init__(self, server: str | FastMCP, domain: str = "", token: TokenProvider | None = None) -> None:
        self.server = server  # la URL del MCP; en los tests, el servidor en memoria
        self.domain = domain
        self.token = token
        self._definitions: list[ToolDefinition] | None = None

    def definitions(self) -> list[ToolDefinition]:
        if self._definitions is None:  # se piden una vez, al arrancar: las tools no cambian mientras corre el agente
            self._definitions = [_definition(tool) for tool in self._run(lambda client: client.list_tools())]
        return self._definitions

    def call(self, call: ToolCall) -> ToolResult:
        try:
            result = self._run(lambda client: client.call_tool(call.name, call.arguments))
        except ToolError as error:  # error de negocio: el modelo lo lee y se lo explica al cliente
            content = json.dumps({"error": str(error)}, ensure_ascii=False)
            return ToolResult(call=call, status=ToolStatus.ERROR, content=content)
        return ToolResult(call=call, status=ToolStatus.OK, content=json.dumps(result.structured_content, ensure_ascii=False))

    def _run[Result](self, action: Callable[[Client], Awaitable[Result]]) -> Result:
        async def run() -> Result:
            async with mcp_client(self.server, self.domain, self.token) as client:
                return await action(client)

        # el agente es síncrono, pero uvicorn lo arma dentro de su event loop: el cliente MCP corre en un hilo con el suyo.
        # ponytail: una conexión por llamada; si un turno usa muchas tools, mantener una sesión abierta
        try:
            with ThreadPoolExecutor(max_workers=1) as thread:
                return thread.submit(asyncio.run, run()).result()
        except ToolError:
            raise
        except Exception as error:  # conexión o timeout: el MCP no está disponible
            raise AgentError(ErrorKind.UPSTREAM, f"no se pudo llamar al MCP: {type(error).__name__}") from error


def _definition(tool: Tool) -> ToolDefinition:
    return ToolDefinition(
        name=tool.name,
        description=tool.description or "",
        parameters=tool.input_schema,
        sensitive=bool(tool.annotations and tool.annotations.destructive_hint),
    )