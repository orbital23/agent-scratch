import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from agent.domain.models import AgentReply, Intent


def test_agent_reply_schema_is_strict():
    schema = to_strict_json_schema(AgentReply)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"intent", "answer"}
    assert "description" in schema["properties"]["answer"]


@pytest.mark.parametrize(
    "data",
    [
        {"intent": "greeting", "answer": "   "},
        {"intent": "greeting", "answer": "Hola", "extra": 1},
        {"intent": "no_existe", "answer": "Hola"},
    ],
)
def test_agent_reply_rejects_invalid_output(data):
    with pytest.raises(ValidationError):
        AgentReply.model_validate(data)


def test_agent_reply_strips_answer():
    assert AgentReply(intent=Intent.GREETING, answer="  Hola  ").answer == "Hola"
