"""Extract allocation defaults from the DI Pipelines operator framework."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.ast_values import (
    evaluate,
    module_constants,
)

_ALLOCATION_VARIABLES = {
    "driver_cores",
    "driver_max_result_size",
    "driver_memory",
    "executor_cores",
    "executor_instances_max",
    "executor_instances_min",
    "executor_memory",
}


@dataclass(frozen=True, slots=True)
class OperatorDefaults:
    """Source-defined resource defaults shared by OperatorFactory jobs."""

    pod_resources: object = None
    spark_variables: tuple[tuple[str, object], ...] = ()


@lru_cache(maxsize=8)
def operator_defaults(repository: Path) -> OperatorDefaults:
    """Parse framework defaults without importing Airflow or provider modules."""
    path = repository.resolve() / "dag-utils" / "operators.py"
    if not path.is_file():
        return OperatorDefaults()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    environment = module_constants(tree)
    variables = _spark_variables(tree, environment)
    return OperatorDefaults(
        pod_resources=environment.get("DEFAULT_POD_JOB_RESOURCES"),
        spark_variables=tuple(sorted(variables.items())),
    )


def _spark_variables(
    tree: ast.Module,
    environment: dict[str, object],
) -> dict[str, object]:
    for statement in tree.body:
        if not isinstance(statement, ast.ClassDef):
            continue
        if statement.name != "SparkSubmitOperatorBuilder":
            continue
        for member in statement.body:
            if not isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if member.name != "default_spark_conf_template_variables":
                continue
            value = _return_value(member)
            local_environment = module_constants(
                ast.Module(body=member.body, type_ignores=[]),
                environment,
            )
            evaluated = evaluate(value, local_environment)
            if isinstance(evaluated, dict):
                return {
                    str(key): item
                    for key, item in evaluated.items()
                    if str(key) in _ALLOCATION_VARIABLES
                }
    return {}


def _return_value(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> ast.AST | None:
    return next(
        (
            statement.value
            for statement in ast.walk(function)
            if isinstance(statement, ast.Return)
        ),
        None,
    )
