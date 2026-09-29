"""Replay sources backed by one captured production-support bundle."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from domain import AgentRequest, AgentResult
from domain.models import Attributes
from workspaces.data_engineering.workflows.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.workflows.prod_support.models import Region


class CaptureReplayError(ValueError):
    """Raised when a captured bundle cannot be replayed safely."""

    @classmethod
    def list_required(cls, path: Path, field: str) -> CaptureReplayError:
        """Return an error for a required list field."""
        return cls(f"{path}: {field} must be a list")

    @classmethod
    def region_missing(cls, region: Region) -> CaptureReplayError:
        """Return an error for a region absent from the capture."""
        return cls(f"captured cluster health does not contain {region.value}")

    @classmethod
    def identifier_required(cls) -> CaptureReplayError:
        """Return an error for a request without an exact identifier."""
        return cls("replay request requires identifier_value")

    @classmethod
    def object_required(cls, path: Path) -> CaptureReplayError:
        """Return an error for a required mapping."""
        return cls(f"{path}: expected an object")

    @classmethod
    def cluster_region_required(cls, path: Path) -> CaptureReplayError:
        """Return an error for a malformed regional observation."""
        return cls(f"{path}: cluster region must be an object")

    @classmethod
    def optional_boolean_required(cls) -> CaptureReplayError:
        """Return an error for a malformed optional boolean."""
        return cls("captured cluster boolean must be true, false, or null")

    @classmethod
    def optional_integer_required(cls) -> CaptureReplayError:
        """Return an error for a malformed optional integer."""
        return cls("captured cluster integer must be an integer or null")

    @classmethod
    def optional_string_required(cls) -> CaptureReplayError:
        """Return an error for malformed optional metadata."""
        return cls("captured resource metadata must be a string or null")


class CapturedClusterHealthSource:
    """Replay captured regional cluster health without production access."""

    def __init__(self, path: Path) -> None:
        """Load one complete cluster-health capture."""
        raw = _read_mapping(path)
        regions = raw.get("regions")
        if not isinstance(regions, list):
            raise CaptureReplayError.list_required(path, "regions")
        self._observations = {
            observation.region: observation
            for observation in (_cluster_observation(item, path) for item in regions)
        }

    async def inspect_health(
        self,
        region: Region,
        restart_window_start: datetime,
        restart_window_end: datetime,
    ) -> RegionalClusterHealth:
        """Return the captured observation for one region."""
        del restart_window_start, restart_window_end
        try:
            return self._observations[region]
        except KeyError as error:
            raise CaptureReplayError.region_missing(region) from error


class CapturedResourceDiscoveryInvoker:
    """Replay captured non-secret client metadata."""

    def __init__(self, path: Path) -> None:
        """Load one Resource Discovery capture."""
        raw = _read_mapping(path)
        lookups = raw.get("lookups")
        if not isinstance(lookups, list):
            raise CaptureReplayError.list_required(path, "lookups")
        self._lookups = {
            str(item["client_id"]): item
            for value in lookups
            if isinstance(value, dict)
            for item in (value,)
        }

    async def run(self, request: AgentRequest) -> AgentResult:
        """Return the captured result for the request's exact client ID."""
        attributes = dict(request.attributes)
        identifier = attributes.get("identifier_value")
        if not isinstance(identifier, str):
            raise CaptureReplayError.identifier_required()
        lookup = self._lookups.get(identifier)
        values: Attributes
        if lookup is None:
            values = (
                ("identifier_kind", "client_id"),
                ("identifier_value", identifier),
                ("status", "not_found"),
                ("match_count", 0),
            )
        else:
            values = (
                ("identifier_kind", "client_id"),
                ("identifier_value", identifier),
                ("status", str(lookup.get("match", "not_found"))),
                ("match_count", 1),
                ("client_name", _optional_string(lookup.get("client_name"))),
                ("environment", _optional_string(lookup.get("environment"))),
                (
                    "reviewed_production_resend_url",
                    _optional_string(lookup.get("reviewed_production_resend_url")),
                ),
                (
                    "routing_source",
                    _optional_string(lookup.get("routing_source")),
                ),
                (
                    "prod_support_ignore",
                    lookup.get("prod_support_ignore") is True,
                ),
            )
        return AgentResult(
            output=f"Captured Resource Discovery result for {identifier}.",
            correlation_id=request.correlation_id,
            tool_calls=("ResourceDiscovery",),
            attributes=values,
        )


def _read_mapping(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CaptureReplayError.object_required(path)
    return raw


def _cluster_observation(
    raw: object,
    path: Path,
) -> RegionalClusterHealth:
    if not isinstance(raw, dict):
        raise CaptureReplayError.cluster_region_required(path)
    observed_at = raw.get("observed_at")
    return RegionalClusterHealth(
        region=Region(str(raw["region"])),
        observed_at=(
            datetime.fromisoformat(str(observed_at))
            if observed_at is not None
            else None
        ),
        application_healthy=_optional_bool(raw.get("application_healthy")),
        pods_healthy=_optional_bool(raw.get("pods_healthy")),
        dags_parsing_healthy=_optional_bool(raw.get("dags_parsing_healthy")),
        active_dag_count=_optional_int(raw.get("active_dag_count")),
        restart_count=_optional_int(raw.get("restart_count")),
        cumulative_restart_count=_optional_int(raw.get("cumulative_restart_count")),
        restart_window_start=_optional_datetime(raw.get("restart_window_start")),
        restart_window_end=_optional_datetime(raw.get("restart_window_end")),
        keda_status=str(raw.get("keda_status", "unknown")),
        symptoms=tuple(str(value) for value in raw.get("symptoms", ())),
        warnings=tuple(str(value) for value in raw.get("warnings", ())),
    )


def _optional_bool(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise CaptureReplayError.optional_boolean_required()


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, int):
        return value
    raise CaptureReplayError.optional_integer_required()


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise CaptureReplayError.optional_string_required()


def _optional_string(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise CaptureReplayError.optional_string_required()
