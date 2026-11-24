import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from agent.domain.errors import AgentError, ErrorKind
from agent.domain.models import ToolCall
from agent.infrastructure.persistence.cosmos_store import CosmosConversationStore


class FakeContainer:
    """The part of ContainerProxy the store uses, with the items in a dict keyed by (partition, id)."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def read_item(self, item: str, partition_key: str) -> dict:
        try:
            return self.items[(partition_key, item)]
        except KeyError:
            raise CosmosResourceNotFoundError(message="not found") from None

    def upsert_item(self, body: dict) -> dict:
        self.items[(body["userId"], body["id"])] = body
        return body


class BrokenContainer:
    def read_item(self, item: str, partition_key: str) -> dict:
        raise CosmosHttpResponseError(status_code=403, message="forbidden")


def store(container=None) -> CosmosConversationStore:
    return CosmosConversationStore(container or FakeContainer())


def test_new_session_has_no_history_and_no_pending_action():
    s = store()
    assert s.get("s1") == []
    assert s.pending("s1") is None


def test_append_keeps_order_and_isolates_sessions():
    container = FakeContainer()
    s = store(container)
    s.append("s1", {"role": "user", "content": "hola"})
    s.append("s1", {"role": "assistant", "content": "qué tal"})
    s.append("s2", {"role": "user", "content": "otra"})

    assert s.get("s1") == [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "qué tal"}]
    assert s.get("s2") == [{"role": "user", "content": "otra"}]
    # the container partition is /userId: the agent has no users, the session is the partition
    assert container.items[("s1", "s1")]["userId"] == "s1"


def test_history_survives_a_new_store_on_the_same_container():
    container = FakeContainer()
    store(container).append("s1", {"role": "user", "content": "hola"})
    store(container).set_pending("s1", ToolCall(id="c1", name="block_card", arguments={"card": "1234"}))

    other_replica = store(container)
    assert other_replica.get("s1") == [{"role": "user", "content": "hola"}]
    assert other_replica.pending("s1") == ToolCall(id="c1", name="block_card", arguments={"card": "1234"})


def test_clearing_the_pending_action_keeps_the_history():
    s = store()
    s.append("s1", {"role": "user", "content": "bloquea"})
    s.set_pending("s1", ToolCall(id="c1", name="block_card", arguments={}))
    s.set_pending("s1", None)

    assert s.pending("s1") is None
    assert s.get("s1") == [{"role": "user", "content": "bloquea"}]


def test_cosmos_failure_becomes_an_upstream_agent_error():
    with pytest.raises(AgentError) as error:
        store(BrokenContainer()).get("s1")
    assert error.value.kind is ErrorKind.UPSTREAM


def test_without_cosmos_endpoint_the_store_is_in_memory():
    from agent.infrastructure.bootstrap import build_store
    from agent.infrastructure.config.settings import CosmosSettings
    from agent.infrastructure.persistence.in_memory_store import InMemoryConversationStore

    assert isinstance(build_store(CosmosSettings(_env_file=None, endpoint="")), InMemoryConversationStore)


def test_cosmos_endpoint_without_database_or_container_does_not_start():
    from agent.infrastructure.bootstrap import build_store
    from agent.infrastructure.config.settings import CosmosSettings

    settings = CosmosSettings(_env_file=None, endpoint="https://x.documents.azure.com:443/", database="workshop", container="")
    with pytest.raises(RuntimeError, match="COSMOS_ENDPOINT requiere COSMOS_DATABASE y COSMOS_CONTAINER"):
        build_store(settings)