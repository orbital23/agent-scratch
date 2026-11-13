"""El mock MCP (dev/mcp/mock_mcp.py): mismo contrato que bank-mcp, filtro por dominio según el header X-Bank-Domain y errores legibles."""

import asyncio
import json
import socket
from pathlib import Path

import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from mock_mcp import DOMAINS, create_server

CONTRACT = Path(__file__).resolve().parents[2] / "dev" / "mcp" / "contract.json"
SENSITIVE = {"request_fee_refund", "request_credit_line_increase", "block_card", "file_claim", "submit_loan_application",
             "update_contact_details"}


def run(coroutine):
    return asyncio.run(coroutine)


async def call(name: str, arguments: dict):
    async with Client(create_server()) as client:
        return await client.call_tool(name, arguments)


def test_same_contract_as_bank_mcp():
    """Si bank-mcp cambia una tool, se copia su contract/tools.json a dev/mcp/contract.json y este test dice qué ajustar."""

    async def tools():
        return sorted(await create_server().list_tools(), key=lambda tool: tool.name)

    mock = [
        {"name": t.name, "domains": sorted(t.tags), "description": t.description,
         "annotations": t.annotations.model_dump(exclude_none=True), "input_schema": t.parameters,
         "output_schema": t.output_schema}
        for t in run(tools())
    ]
    assert mock == json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_sensitive_actions_are_marked_destructive():
    async def tools():
        return await create_server().list_tools()

    for tool in run(tools()):
        assert tool.annotations.destructive_hint is (tool.name in SENSITIVE), tool.name


def test_duplicated_charge_of_the_course_case():
    result = run(call("get_transactions", {"customer_id": "CUS-1001", "limit": 2}))
    first, second = result.structured_content["result"]
    assert first["amount"] == second["amount"] and first["description"] == second["description"]


def test_business_errors_are_readable():
    with pytest.raises(ToolError, match="El cliente CUS-9999 no existe"):
        run(call("get_cards", {"customer_id": "CUS-9999"}))
    with pytest.raises(ToolError, match="no admite devolución"):
        run(call("request_fee_refund", {"fee_id": "FEE-4001", "reason": "cobro indebido"}))


def test_block_card_twice_in_the_same_server():
    async def twice():
        async with Client(create_server()) as client:
            await client.call_tool("block_card", {"card_id": "CRD-2001", "reason": "robo"})
            await client.call_tool("block_card", {"card_id": "CRD-2001", "reason": "robo"})

    with pytest.raises(ToolError, match="ya está bloqueada"):
        run(twice())
    # un servidor nuevo arranca con los datos de siempre
    assert run(call("get_cards", {"customer_id": "CUS-1001"})).structured_content["result"][0]["status"] == "active"


def test_installment_is_calculated_not_estimated():
    result = run(call("simulate_installment", {"amount": 20000, "term_months": 24}))
    assert result.structured_content["monthly_installment"] == 985.64


def test_each_domain_sees_only_its_tools():
    """Por HTTP, como lo usa el agente: el header X-Bank-Domain filtra; sin él se ven las 15."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    async def check():
        server = uvicorn.Server(uvicorn.Config(create_server().http_app(path="/mcp"), port=port, log_level="warning"))
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.05)
        try:
            url = f"http://127.0.0.1:{port}/mcp"
            async with Client(url) as client:
                assert len(await client.list_tools()) == 15
            visible = {}
            for domain in DOMAINS:
                async with Client(StreamableHttpTransport(url, headers={"X-Bank-Domain": domain})) as client:
                    visible[domain] = {tool.name for tool in await client.list_tools()}
            async with Client(StreamableHttpTransport(url, headers={"X-Bank-Domain": "fees"})) as client:
                with pytest.raises(ToolError, match="Unknown tool"):
                    await client.call_tool("block_card", {"card_id": "CRD-2001", "reason": "robo"})
            return visible
        finally:
            server.should_exit = True
            await task

    visible = run(check())
    assert visible["fraud"] == {"get_transactions", "get_claim_status", "block_card", "file_claim"}
    assert visible["loans"] == {"simulate_installment", "get_credit_profile", "submit_loan_application"}
    assert all(len(tools) in (3, 4) for tools in visible.values())