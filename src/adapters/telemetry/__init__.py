"""Configure OpenTelemetry exporters at application composition roots."""

from adapters.telemetry.configuration import (
    TelemetryConfiguration,
    configure_telemetry,
)

__all__ = ["TelemetryConfiguration", "configure_telemetry"]
