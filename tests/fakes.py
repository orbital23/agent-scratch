"""Implementaciones de prueba del puerto ChatModel: sin red ni Foundry."""

from agent.domain.models import AgentReply, Intent, Message


class FakeChatModel:
    RULES = [
        (Intent.SENSITIVE_ACTION, ("bloque", "robaron", "robo", "perdí", "registrar reclamo")),
        (Intent.DATA_QUERY, ("mis movimientos", "estado de mi reclamo", "estado del reclamo")),
        (Intent.PRODUCT_QUESTION, ("fraude", "contracargo", "plazo", "reclamo", "no reconozco")),
        (Intent.GREETING, ("hola", "buenos", "buenas", "gracias", "adiós")),
    ]

    def complete(self, messages: list[Message]) -> AgentReply:
        text = messages[-1]["content"].lower()
        intent = next(
            (intent for intent, words in self.RULES if any(word in text for word in words)),
            Intent.OUT_OF_SCOPE,
        )
        return AgentReply(intent=intent, answer=f"[fake] intención detectada: {intent}")


class RecordingChatModel(FakeChatModel):
    def __init__(self) -> None:
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> AgentReply:
        self.calls.append(messages)
        return super().complete(messages)
