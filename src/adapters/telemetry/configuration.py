"""Configure an OpenTelemetry tracer provider for visible local traces."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

EXPORTER_ENV = "Q2_OTEL_EXPORTER"
SERVICE_NAME_ENV = "OTEL_SERVICE_NAME"


@dataclass(frozen=True, slots=True)
class TelemetryConfiguration:
    """Describe the effective process-level telemetry configuration."""

    exporter: str
    service_name: str
    configured: bool


def configure_telemetry(
    *,
    default_service_name: str,
) -> TelemetryConfiguration:
    """Configure immediate stderr trace export unless explicitly disabled."""
    exporter = os.environ.get(EXPORTER_ENV, "console").strip().lower()
    service_name = os.environ.get(SERVICE_NAME_ENV, default_service_name).strip()
    if not service_name:
        message = f"{SERVICE_NAME_ENV} must not be empty"
        raise ValueError(message)
    if exporter not in {"console", "none"}:
        message = f"{EXPORTER_ENV} must be 'console' or 'none', got {exporter!r}"
        raise ValueError(message)
    if exporter == "none":
        return TelemetryConfiguration(exporter, service_name, configured=False)

    existing = trace.get_tracer_provider()
    if isinstance(existing, TracerProvider):
        return TelemetryConfiguration(exporter, service_name, configured=False)

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
    )
    trace.set_tracer_provider(provider)
    return TelemetryConfiguration(exporter, service_name, configured=True)
