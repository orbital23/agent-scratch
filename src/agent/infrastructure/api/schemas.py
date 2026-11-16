"""Contrato HTTP del agente (adaptador de entrada)."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from agent.domain.models import Intent

UserMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatRequest(BaseModel):
    session_id: UUID | None = None
    message: UserMessage


class ChatResponse(BaseModel):
    session_id: UUID
    intent: Intent
    answer: str


# TODO S2: ChatResponse.usage (modelos, latencia y tokens) y ErrorResponse.
# Regla: estos contratos solo crecen con campos opcionales (T2 citations, T3 pending_action).
