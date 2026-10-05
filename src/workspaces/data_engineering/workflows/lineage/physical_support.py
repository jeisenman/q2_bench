"""Static function and OperatorFactory recognition helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.ast_values import (
    call_name,
    evaluate,
)
from workspaces.data_engineering.workflows.lineage.source import SourceModule


@dataclass(frozen=True, slots=True)
class PhysicalJobContext:
    """Static values and source identity used to construct one physical job."""

    module: SourceModule
    variable: str
    values: dict[str, object]
    prefix: str
    repository: Path


def bind_arguments(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    arguments: tuple[object, ...],
    keywords: dict[str, object],
    module: SourceModule,
) -> dict[str, object]:
    """Bind safe static values to a Python function signature."""
    parameters = [*function.args.posonlyargs, *function.args.args]
    bound = {
        parameter.arg: arguments[index]
        for index, parameter in enumerate(parameters[: len(arguments)])
    }
    bound.update(keywords)
    default_offset = len(parameters) - len(function.args.defaults)
    for index, parameter in enumerate(parameters):
        if parameter.arg in bound or index < default_offset:
            continue
        bound[parameter.arg] = evaluate(
            function.args.defaults[index - default_offset],
            module.constants,
        )
    for parameter in parameters:
        bound.setdefault(parameter.arg, f"{{{parameter.arg}}}")
    return bound


def operator_factory_call(value: ast.AST) -> tuple[ast.Call, ast.Call] | None:
    """Return the factory and operate calls from an OperatorFactory expression."""
    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
        return None
    if value.func.attr != "operate" or not isinstance(value.func.value, ast.Call):
        return None
    factory = value.func.value
    return (factory, value) if call_name(factory).endswith("OperatorFactory") else None


def is_task_function(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return whether a function can declare or delegate task construction."""
    return any(
        isinstance(node, ast.Call)
        and (
            call_name(node).endswith("OperatorFactory")
            or call_name(node).lstrip("_").startswith(("get_", "build_"))
        )
        for node in ast.walk(function)
    )
