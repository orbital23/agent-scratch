"""Contrato HTTP del agente. Solo crece con campos opcionales: T2 citations, T3 tools y pending_action, T4 trace_id."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from agent.domain.errors import ErrorKind
from agent.domain.knowledge import Citation
from agent.domain.models import Decision, Intent, ToolCall, ToolResult, Usage

UserMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatRequest(BaseModel):
    session_id: UUID | None = None
    message: UserMessage


class ChatResponse(BaseModel):
    session_id: UUID
    intent: Intent
    answer: str
    usage: Usage
    citations: list[Citation] = []
    tools: list[ToolResult] = []  # las tools que usó el agente en el turno, con su resultado
    pending_action: ToolCall | None = None  # S8: la acción sensible que espera la decisión del asesor


class ActionDecision(BaseModel):
    """S8: lo que decide el asesor sobre la acción pendiente de una sesión. action_id es el id de pending_action."""

    session_id: UUID
    action_id: str
    decision: Decision


class ErrorResponse(BaseModel):
    error: ErrorKind
    detail: str