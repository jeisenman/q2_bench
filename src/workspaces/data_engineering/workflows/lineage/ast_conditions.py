"""Condition evaluation for concrete lineage allocation profiles."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Mapping
from typing import Any, cast

Evaluator = Callable[[ast.AST | None, Mapping[str, object]], object]


def truth_value(
    node: ast.AST,
    environment: Mapping[str, object],
    evaluator: Evaluator,
) -> bool | None:
    """Return a branch decision when all source values are resolvable."""
    value = evaluator(node, environment)
    if is_symbolic(value, node):
        return None
    return bool(value)


def boolean_value(
    node: ast.BoolOp,
    environment: Mapping[str, object],
    evaluator: Evaluator,
) -> object:
    """Evaluate a Python and/or expression without running source code."""
    values = [evaluator(value, environment) for value in node.values]
    if any(
        is_symbolic(value, source)
        for value, source in zip(values, node.values, strict=True)
    ):
        return ast.unparse(node)
    if isinstance(node.op, ast.And):
        return next((value for value in values if not value), values[-1])
    return next((value for value in values if value), values[-1])


def comparison_value(
    node: ast.Compare,
    environment: Mapping[str, object],
    evaluator: Evaluator,
) -> object:
    """Evaluate a resolvable chained comparison."""
    sources = (node.left, *node.comparators)
    values = [evaluator(item, environment) for item in sources]
    if any(
        is_symbolic(value, source)
        for value, source in zip(values, sources, strict=True)
    ):
        return ast.unparse(node)
    return all(
        _compare_pair(left, operation, right)
        for left, operation, right in zip(
            values[:-1],
            node.ops,
            values[1:],
            strict=True,
        )
    )


def is_symbolic(value: object, source: ast.AST) -> bool:
    """Return whether a static value represents an unresolved expression."""
    if not isinstance(value, str):
        return False
    return value == ast.unparse(source) or (
        value.startswith("{") and value.endswith("}")
    )


def _compare_pair(left: object, operation: ast.cmpop, right: object) -> bool:
    left_value = cast(Any, left)
    right_value = cast(Any, right)
    try:
        if isinstance(operation, ast.Eq | ast.Is):
            result = operator.eq(left_value, right_value)
        elif isinstance(operation, ast.NotEq | ast.IsNot):
            result = operator.ne(left_value, right_value)
        elif isinstance(operation, ast.In):
            result = operator.contains(right_value, left_value)
        elif isinstance(operation, ast.NotIn):
            result = not operator.contains(right_value, left_value)
        elif isinstance(operation, ast.Lt):
            result = operator.lt(left_value, right_value)
        elif isinstance(operation, ast.LtE):
            result = operator.le(left_value, right_value)
        elif isinstance(operation, ast.Gt):
            result = operator.gt(left_value, right_value)
        elif isinstance(operation, ast.GtE):
            result = operator.ge(left_value, right_value)
        else:
            result = False
    except TypeError:
        result = False
    return bool(result)
