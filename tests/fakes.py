"""Implementaciones de prueba del puerto ChatModel: sin red ni Foundry."""

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import AgentReply, Intent, Message, ModelResult, Usage


class FakeChatModel:
    # ponytail: heurística naive por palabras clave, solo para tests
    RULES = [
        (Intent.SENSITIVE_ACTION, ("bloque", "robaron", "robo", "perdí", "registrar reclamo")),
        (Intent.DATA_QUERY, ("mis movimientos", "estado de mi reclamo", "estado del reclamo")),
        (Intent.PRODUCT_QUESTION, ("fraude", "contracargo", "plazo", "reclamo", "no reconozco")),
        (Intent.GREETING, ("hola", "buenos", "buenas", "gracias", "adiós")),
    ]

    def complete(self, messages: list[Message]) -> ModelResult:
        text = messages[-1]["content"].lower()
        intent = next((intent for intent, words in self.RULES if any(word in text for word in words)), Intent.OUT_OF_SCOPE)
        reply = AgentReply(intent=intent, answer=f"[fake] intención detectada: {intent}")
        usage = Usage(models=["fake"], llm_calls=1, prompt_tokens=10, completion_tokens=5)
        return ModelResult(reply=reply, usage=usage)


class RecordingChatModel(FakeChatModel):
    def __init__(self) -> None:
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> ModelResult:
        self.calls.append(messages)
        return super().complete(messages)


class FailingChatModel:
    def __init__(self, kind: ErrorKind) -> None:
        self.kind = kind

    def complete(self, messages: list[Message]) -> ModelResult:
        raise AgentError(self.kind, "falla simulada")