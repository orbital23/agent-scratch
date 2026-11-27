from agent.infrastructure import bootstrap
from agent.infrastructure.config.settings import Settings


def test_without_connection_string_there_is_no_telemetry(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "configure_azure_monitor", lambda **kwargs: calls.append(kwargs))

    assert bootstrap.configure_telemetry(Settings(_env_file=None, applicationinsights_connection_string="")) is False
    assert calls == []


def test_with_connection_string_traces_go_to_azure_monitor_with_entra_id(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "configure_azure_monitor", lambda **kwargs: calls.append(kwargs))
    settings = Settings(_env_file=None, applicationinsights_connection_string="InstrumentationKey=00000000-0000-0000-0000-000000000000")

    assert bootstrap.configure_telemetry(settings) is True
    (kwargs,) = calls
    assert kwargs["connection_string"] == settings.applicationinsights_connection_string
    assert kwargs["credential"] is not None  # sin la llave de la cadena: el envío se autentica con Entra ID
    assert kwargs["logger_name"] == "agent"  # solo los logs del agente, no los de cada librería