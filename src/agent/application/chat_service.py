from agent.domain.models import AgentTurn, Message
from agent.domain.ports import ChatModel, ConversationStore


class ChatService:
    """Caso de uso: resolver un turno de conversación. Solo conoce puertos, nunca infraestructura."""

    def __init__(self, model: ChatModel, store: ConversationStore, system_prompt: str, max_turns: int) -> None:
        self.model = model
        self.store = store
        self.system_prompt = system_prompt
        self.max_turns = max_turns

    def handle(self, session_id: str, message: str) -> AgentTurn:
        user: Message = {"role": "user", "content": message}
        recent = self.store.get(session_id)[-self.max_turns * 2 :]
        result = self.model.complete([{"role": "system", "content": self.system_prompt}, *recent, user])
        # se guarda solo si el modelo respondió: un error no deja turnos a medias
        self.store.append(session_id, user)
        self.store.append(session_id, {"role": "assistant", "content": result.reply.answer})
        return AgentTurn(reply=result.reply, usage=result.usage)