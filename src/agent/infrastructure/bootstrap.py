"""Composition root: conecta cada puerto del dominio con su implementación.

Arranque: uv run uvicorn agent.infrastructure.bootstrap:create_app --factory --reload
"""

import logging

from fastapi import FastAPI

from agent.application.chat_service import ChatService
from agent.domain.errors import AgentError
from agent.domain.ports import ChatModel
from agent.infrastructure.api.routes import agent_error_handler, build_router
from agent.infrastructure.config.settings import FoundrySettings, Settings
from agent.infrastructure.llm.credentials import build_credential
from agent.infrastructure.llm.foundry_chat_model import FoundryChatModel
from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore
from agent.infrastructure.prompts.loader import load_prompt

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def build_chat_model(foundry: FoundrySettings) -> ChatModel:
    if not foundry.endpoint:
        raise RuntimeError("Falta FOUNDRY_ENDPOINT. Copia .env.example a .env y complétalo.")
    log.info("Foundry auth provider: %s", foundry.auth_provider)
    return FoundryChatModel(
        endpoint=foundry.endpoint,
        credential=build_credential(foundry.auth_provider, foundry.api_key),
        deployment=foundry.deployment,
        timeout_s=foundry.timeout_s,
        max_retries=foundry.max_retries,
    )


def create_app(chat_model: ChatModel | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    chat_service = ChatService(
        model=chat_model or build_chat_model(settings.foundry),
        store=InMemoryConversationStore(),
        system_prompt=load_prompt(settings.domain),
        max_turns=settings.max_turns,
    )
    app = FastAPI(title=f"agent-{settings.domain}")
    app.include_router(build_router(chat_service))
    app.add_exception_handler(AgentError, agent_error_handler)
    return app