from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Message = dict[str, Any]  # formato OpenAI: {"role": "system" | "user" | "assistant", "content": ...}


class Intent(StrEnum):
    PRODUCT_QUESTION = "product_question"  # T2: RAG
    DATA_QUERY = "data_query"  # T3: tool MCP
    SENSITIVE_ACTION = "sensitive_action"  # T3: HITL
    GREETING = "greeting"
    OUT_OF_SCOPE = "out_of_scope"


def _not_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("no puede estar vacío")
    return value


class AgentReply(BaseModel):
    """Respuesta final del modelo (structured output)."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent = Field(description="Intención del último mensaje del cliente.")
    answer: Annotated[str, AfterValidator(_not_blank)] = Field(
        description="Respuesta al cliente en español, breve y clara."
    )


# TODO S2: Usage (modelos, llamadas, latencia, tokens; sumable), ModelResult (reply + usage)
#          y AgentTurn (resultado de un turno: reply + usage).
