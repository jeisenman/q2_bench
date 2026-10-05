"""Extract explicit resource settings from OperatorFactory calls."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.allocation_models import (
    ResourceAllocation,
)
from workspaces.data_engineering.workflows.lineage.ast_values import (
    evaluate,
    stringify,
)
from workspaces.data_engineering.workflows.lineage.operator_defaults import (
    operator_defaults,
)


def resource_allocation(
    factory: ast.Call,
    compute: str,
    values: dict[str, object],
    repository: Path,
) -> ResourceAllocation:
    """Return the compute backend and explicit resource configuration."""
    arguments = _call_arguments(factory, values)
    defaults = operator_defaults(repository)
    operator_args = _as_mapping(arguments.get("override_operator_args"))
    resources = operator_args.get("container_resources")
    if resources is None and compute == "k8s_pod":
        resources = values.get(
            "DEFAULT_POD_JOB_RESOURCES",
            defaults.pod_resources,
        )
    spark_variables = dict(defaults.spark_variables) if compute == "spark" else {}
    if compute == "spark":
        spark_variables.update(
            _as_mapping(arguments.get("override_spark_conf_template_variables"))
        )
    spark_configuration = (
        _flatten_mapping(arguments.get("override_spark_conf_template"))
        if compute == "spark"
        else ()
    )
    return ResourceAllocation(
        compute=compute,
        container_resources=_flatten_mapping(resources),
        spark_configuration=spark_configuration,
        spark_variables=_flatten_mapping(spark_variables),
    )


def _call_arguments(
    call: ast.Call,
    values: dict[str, object],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for keyword in call.keywords:
        value = evaluate(keyword.value, values)
        if keyword.arg is None:
            result.update(_as_mapping(value))
        else:
            result[keyword.arg] = value
    return result


def _as_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if not str(key).startswith("__q2_")
    }


def _flatten_mapping(value: object) -> tuple[tuple[str, str], ...]:
    flattened: dict[str, str] = {}

    def visit(prefix: str, item: object) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                name = str(key)
                if name.startswith("__q2_"):
                    continue
                visit(f"{prefix}.{name}" if prefix else name, nested)
            return
        if prefix:
            flattened[prefix] = stringify(item)

    visit("", value)
    return tuple(sorted(flattened.items()))
