from uuid import uuid4

from fastapi import APIRouter

from agent.application.chat_service import ChatService
from agent.infrastructure.api.schemas import ChatRequest, ChatResponse


def build_router(chat_service: ChatService) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/chat")
    def chat(chat_request: ChatRequest) -> ChatResponse:
        session_id = chat_request.session_id or uuid4()
        reply = chat_service.handle(str(session_id), chat_request.message)
        return ChatResponse(session_id=session_id, intent=reply.intent, answer=reply.answer)

    # TODO S2: handler de AgentError → HTTP: timeout 504, rate limit 429, salida inválida 502.

    return router
