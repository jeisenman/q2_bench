"""Safe static values for DI Pipelines resource-allocation helpers."""

from __future__ import annotations

from collections.abc import Mapping

NOT_SPECIAL = object()
_STATIC_TYPE = "__q2_static_type__"


def constructor_value(
    name: str,
    args: list[object],
    kwargs: dict[str, object],
) -> object:
    """Resolve supported resource and client-override constructors."""
    if name.endswith("V1ResourceRequirements"):
        return {
            _STATIC_TYPE: "resources",
            "limits": kwargs.get("limits", {}),
            "requests": kwargs.get("requests", {}),
        }
    if name.endswith("ClientArgOverrides"):
        return _override_object("client_args", args, kwargs)
    if name.endswith("ClientSparkConfOverrides"):
        return _override_object("spark_conf", args, kwargs)
    return NOT_SPECIAL


def method_value(
    receiver: Mapping[object, object],
    method: str,
    kwargs: dict[str, object],
) -> object:
    """Resolve methods on supported client-allocation objects."""
    kind = receiver.get(_STATIC_TYPE)
    if kind not in {"client_args", "spark_conf"}:
        return NOT_SPECIAL
    default = mapping_object(receiver.get("default"))
    overrides = receiver.get("client_overrides")
    backfill_values = mapping_object(receiver.get("backfill_overrides"))
    client_id = kwargs.get("client_id")
    backfill = bool(kwargs.get("backfill", False))
    selected = backfill_values if backfill else {}
    if not backfill and client_id and isinstance(overrides, Mapping):
        selected = mapping_object(overrides.get(client_id))
    combined = {**default, **selected}
    if kind == "client_args" and method == "args":
        return combined
    if kind == "client_args" and method == "compute":
        return "k8s_pod" if "container_resources" in combined else "batch"
    if kind == "spark_conf" and method == "spark_conf":
        return combined
    return NOT_SPECIAL


def mapping_object(value: object) -> dict[str, object]:
    """Return a normalized mapping from an already evaluated value."""
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items() if key != _STATIC_TYPE}


def _override_object(
    kind: str,
    args: list[object],
    kwargs: dict[str, object],
) -> dict[str, object]:
    names = ("default", "client_overrides", "backfill_overrides")
    values = {
        name: kwargs.get(name, args[index] if len(args) > index else {})
        for index, name in enumerate(names)
    }
    return {_STATIC_TYPE: kind, **values}
