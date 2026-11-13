import pytest
from fakes import FakeChatModel, FakeEmbedder, FakeKnowledgeBase, FakeTools
from fastapi.testclient import TestClient

from agent.infrastructure.bootstrap import build_tools, create_app
from agent.infrastructure.config.settings import FoundrySettings, IngestSettings, KnowledgeBaseKind, McpSettings, Settings


def test_health():
    settings = Settings(_env_file=None, foundry=FoundrySettings(_env_file=None, auth_provider="api_key"))
    app = create_app(chat_model=FakeChatModel(), settings=settings, embedder=FakeEmbedder(), knowledge_base=FakeKnowledgeBase(),
                     tools=FakeTools([]))
    response = TestClient(app).get("/health")
    assert response.json() == {"status": "ok"}


def test_agent_does_not_start_with_an_empty_knowledge_base(tmp_path):
    settings = Settings(
        _env_file=None,
        foundry=FoundrySettings(_env_file=None, auth_provider="api_key"),
        ingest=IngestSettings(_env_file=None, data_dir=tmp_path),
        knowledge_base=KnowledgeBaseKind.LOCAL,
    )
    # sin knowledge_base inyectada, el agente arma la de la configuración: una base local recién creada, sin chunks
    with pytest.raises(RuntimeError, match="está vacía"):
        create_app(chat_model=FakeChatModel(), settings=settings, embedder=FakeEmbedder())


def test_a_local_mcp_that_is_down_asks_to_start_the_mock():
    with pytest.raises(RuntimeError, match="Levanta el mock"):
        build_tools(McpSettings(_env_file=None, url="http://127.0.0.1:9/mcp"), "fees")


def test_a_remote_mcp_without_scope_asks_for_mcp_scope():
    with pytest.raises(RuntimeError, match="falta MCP_SCOPE"):
        build_tools(McpSettings(_env_file=None, url="http://mcp.invalid/mcp"), "fees")