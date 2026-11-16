from uuid import UUID

import pytest
from fakes import FailingChatModel, FakeChatModel
from fastapi.testclient import TestClient

from agent.domain.errors import ErrorKind
from agent.infrastructure.bootstrap import create_app
from agent.infrastructure.config.settings import FoundrySettings, Settings


def make_client(chat_model) -> TestClient:
    settings = Settings(_env_file=None, foundry=FoundrySettings(_env_file=None, auth_provider="api_key"))
    return TestClient(create_app(chat_model=chat_model, settings=settings))


# las 5 conversaciones de prueba del entregable de la semana 1
CONVERSATIONS = [
    ("Hola, buenos días", "greeting"),
    ("Me robaron la tarjeta, ¿qué hago?", "sensitive_action"),
    ("¿Cuál es el plazo para presentar un reclamo?", "product_question"),
    ("Quiero ver mis movimientos de ayer", "data_query"),
    ("¿A cuánto está el dólar hoy?", "out_of_scope"),
]


@pytest.mark.parametrize(("message", "intent"), CONVERSATIONS)
def test_chat_returns_typed_reply(message, intent):
    response = make_client(FakeChatModel()).post("/chat", json={"message": message})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == intent
    assert body["answer"]
    assert body["usage"]["llm_calls"] == 1
    UUID(body["session_id"])


def test_chat_keeps_session_id():
    client = make_client(FakeChatModel())
    first = client.post("/chat", json={"message": "Hola"}).json()
    second = client.post("/chat", json={"session_id": first["session_id"], "message": "Gracias"}).json()
    assert second["session_id"] == first["session_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 2001},
        {"session_id": "no-es-uuid", "message": "Hola"},
        {},
    ],
)
def test_invalid_request_is_422(payload):
    assert make_client(FakeChatModel()).post("/chat", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        (ErrorKind.TIMEOUT, 504),
        (ErrorKind.RATE_LIMIT, 429),
        (ErrorKind.INVALID_OUTPUT, 502),
        (ErrorKind.UPSTREAM, 502),
    ],
)
def test_agent_errors_map_to_http(kind, status):
    response = make_client(FailingChatModel(kind)).post("/chat", json={"message": "Hola"})

    assert response.status_code == status
    assert response.json() == {"error": kind.value, "detail": "falla simulada"}