from agent.domain.models import AgentReply, Message
from agent.domain.ports import ChatModel, ConversationStore


class ChatService:
    """Caso de uso: resolver un turno de conversación. Solo conoce puertos, nunca infraestructura."""

    def __init__(self, model: ChatModel, store: ConversationStore, system_prompt: str, max_turns: int) -> None:
        self.model = model
        self.store = store
        self.system_prompt = system_prompt
        self.max_turns = max_turns

    def handle(self, session_id: str, message: str) -> AgentReply:
        user: Message = {"role": "user", "content": message}
        recent = self.store.get(session_id)[-self.max_turns * 2 :]
        # TODO S2: guardar el turno en el historial solo si el modelo respondió y devolver AgentTurn.
        return self.model.complete(
            [{"role": "system", "content": self.system_prompt}, *recent, user]
        )
