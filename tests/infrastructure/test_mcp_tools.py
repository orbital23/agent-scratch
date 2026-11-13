"""McpTools contra el mock MCP en memoria: las mismas tools y errores que verá el agente, sin red."""

import asyncio
import json

import pytest
from mock_mcp import create_server

from agent.domain.errors import AgentError
from agent.domain.models import ToolCall, ToolStatus
from agent.infrastructure.mcp.mcp_tools import DOMAIN_HEADER, McpTools, mcp_client


def test_definitions_mark_the_sensitive_actions():
    definitions = {tool.name: tool for tool in McpTools(create_server()).definitions()}

    assert len(definitions) == 15
    assert definitions["request_fee_refund"].sensitive
    assert not definitions["get_charged_fees"].sensitive
    assert "customer_id" in definitions["get_charged_fees"].parameters["properties"]


def test_a_query_returns_the_structured_content():
    call = ToolCall(id="c1", name="get_charged_fees", arguments={"customer_id": "CUS-1001"})
    result = McpTools(create_server()).call(call)

    assert result.status == ToolStatus.OK
    assert [fee["id"] for fee in json.loads(result.content)["result"]] == ["FEE-4001", "FEE-4002"]


def test_a_business_error_goes_back_to_the_model():
    call = ToolCall(id="c1", name="get_cards", arguments={"customer_id": "CUS-9999"})
    result = McpTools(create_server()).call(call)

    assert result.status == ToolStatus.ERROR
    assert "CUS-9999 no existe" in result.content


def test_an_unreachable_mcp_is_an_agent_error():
    with pytest.raises(AgentError, match="no se pudo llamar al MCP"):
        McpTools("http://127.0.0.1:9/mcp", "fees").definitions()


def test_the_agent_tells_the_mcp_its_domain():
    assert mcp_client("http://127.0.0.1:8200/mcp", "fees").transport.headers == {DOMAIN_HEADER: "fees"}


def test_with_a_token_the_agent_sends_it_as_bearer():
    client = mcp_client("https://mcp.example/mcp", "fees", token=lambda: "token-1")

    assert client.transport.headers == {DOMAIN_HEADER: "fees", "Authorization": "Bearer token-1"}


def test_it_also_works_inside_an_event_loop():
    """uvicorn arma el agente dentro de su event loop: ahí asyncio.run() solo no funciona."""

    async def inside_uvicorn():
        return McpTools(create_server()).definitions()

    assert len(asyncio.run(inside_uvicorn())) == 15