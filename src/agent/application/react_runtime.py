import json
from collections.abc import Callable, Iterator

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import Message, ModelResult, RuntimeEvent, ToolCall, ToolDefinition, ToolRequest, ToolResult, Usage
from agent.domain.ports import ChatModel


class ReactRuntime:
    """Implementa AgentRuntime con el ciclo ReAct propio (S6): el modelo pide tools, se ejecutan, vuelve a preguntar."""

    def __init__(self, model: ChatModel) -> None:
        self.model = model

    def run(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        run_tool: Callable[[ToolCall], ToolResult],
        max_rounds: int,
    ) -> Iterator[RuntimeEvent]:
        messages, usage = list(messages), Usage()
        for _ in range(max_rounds):
            for event in self.model.stream(messages, tools):
                match event:
                    case ModelResult():
                        yield event.model_copy(update={"usage": usage + event.usage})
                        return
                    case ToolRequest(calls=calls):
                        usage += event.usage
                    case _:
                        yield event
            messages.append(_assistant_asking(calls))
            for call in calls:
                yield call
                result = run_tool(call)
                yield result
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result.content})
        raise AgentError(ErrorKind.INVALID_OUTPUT, f"el modelo pidió tools {max_rounds} veces seguidas sin responder")


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