import asyncio

import pytest
from fakes import FakeTools

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import ToolCall, ToolResult
from agent.infrastructure.llm.agent_framework_runtime import AgentFrameworkRuntime, _as_function

FEES_TOOL = FakeTools.DEFINITIONS[0]


def make_runtime() -> AgentFrameworkRuntime:
    return AgentFrameworkRuntime("https://foundry.example", "api-key", "decision-1", timeout_s=5, max_retries=0)


def test_tool_runs_through_run_tool_and_reports_the_call_and_its_result():
    tools, events = FakeTools(), []
    function = _as_function(FEES_TOOL, tools.call, events.append)

    asyncio.run(function.invoke(arguments={"customer_id": "CUS-1001"}))

    call, result = events
    assert isinstance(call, ToolCall) and call.name == "get_charged_fees"
    assert call.arguments == {"customer_id": "CUS-1001"}
    assert isinstance(result, ToolResult) and result.call == call
    assert tools.executed == ["get_charged_fees"]  # la tool la ejecuta run_tool, no Agent Framework


def test_tool_keeps_the_schema_from_the_mcp():
    assert _as_function(FEES_TOOL, FakeTools().call, print).parameters() == FEES_TOOL.parameters


def test_failure_inside_agent_framework_becomes_an_agent_error(monkeypatch):
    async def failing(*args):
        yield ToolCall(id="c1", name="get_charged_fees", arguments={})
        raise ConnectionError("se cayó Foundry")

    runtime = make_runtime()
    monkeypatch.setattr(runtime, "_events", failing)
    events = runtime.run([], [], FakeTools().call, max_rounds=3)

    assert next(events).name == "get_charged_fees"  # lo que llegó antes de la falla ya se entregó
    with pytest.raises(AgentError) as error:
        next(events)
    assert error.value.kind is ErrorKind.UPSTREAM
    assert "ConnectionError" in error.value.detail