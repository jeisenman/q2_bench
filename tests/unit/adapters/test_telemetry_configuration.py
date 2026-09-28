import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from adapters.telemetry import configure_telemetry
from adapters.telemetry.configuration import EXPORTER_ENV, SERVICE_NAME_ENV


def _unconfigured_provider() -> object:
    return object()


def test_console_exporter_configures_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[TracerProvider] = []
    monkeypatch.delenv(EXPORTER_ENV, raising=False)
    monkeypatch.delenv(SERVICE_NAME_ENV, raising=False)
    monkeypatch.setattr(trace, "get_tracer_provider", _unconfigured_provider)
    monkeypatch.setattr(trace, "set_tracer_provider", configured.append)

    result = configure_telemetry(default_service_name="prod-support")

    assert result.configured is True
    assert result.exporter == "console"
    assert result.service_name == "prod-support"
    assert len(configured) == 1


def test_export_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXPORTER_ENV, "none")

    result = configure_telemetry(default_service_name="prod-support")

    assert result.configured is False


def test_invalid_exporter_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXPORTER_ENV, "unknown")

    with pytest.raises(ValueError, match=EXPORTER_ENV):
        configure_telemetry(default_service_name="prod-support")
