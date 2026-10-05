"""Safe static evaluation for source-controlled Python lineage metadata."""

from __future__ import annotations

import ast
import operator
from collections.abc import Iterable, Mapping

from workspaces.data_engineering.workflows.lineage.ast_allocation_values import (
    NOT_SPECIAL,
    constructor_value,
    method_value,
)
from workspaces.data_engineering.workflows.lineage.ast_conditions import (
    boolean_value,
    comparison_value,
)
from workspaces.data_engineering.workflows.lineage.ast_conditions import (
    truth_value as condition_truth_value,
)

StaticEnvironment = Mapping[str, object]
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
}
_UNHANDLED = object()


def evaluate(node: ast.AST | None, environment: StaticEnvironment) -> object:
    """Evaluate safe literals and preserve unknown expressions symbolically."""
    if node is None:
        return None
    for resolver in (_simple, _collection, _expression):
        result = resolver(node, environment)
        if result is not _UNHANDLED:
            return result
    return ast.unparse(node)


def truth_value(node: ast.AST, environment: StaticEnvironment) -> bool | None:
    """Return a concrete branch decision when values are resolvable."""
    return condition_truth_value(node, environment, evaluate)


def string_value(node: ast.AST | None, environment: StaticEnvironment) -> str:
    """Return a normalized string for one static expression."""
    value = evaluate(node, environment)
    return str(value)


def mapping_value(
    node: ast.AST | None,
    environment: StaticEnvironment,
) -> dict[str, object]:
    """Return a string-keyed mapping or an empty mapping."""
    value = evaluate(node, environment)
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def stringify(value: object) -> str:
    """Return a stable scalar representation for extracted metadata."""
    if value is None:
        return ""
    if isinstance(value, dict | list | tuple | set):
        return repr(value)
    return str(value)


def module_constants(
    tree: ast.Module,
    initial: StaticEnvironment | None = None,
) -> dict[str, object]:
    """Evaluate module-level constant assignments in source order."""
    environment: dict[str, object] = dict(initial or {})
    for statement in tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign):
            continue
        value_node = statement.value
        if value_node is None:
            continue
        value = evaluate(value_node, environment)
        for name in assignment_names(statement):
            environment[name] = value
    return environment


def assignment_names(statement: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    """Return simple names assigned by one statement."""
    targets = (
        statement.targets if isinstance(statement, ast.Assign) else [statement.target]
    )
    names: list[str] = []
    for target in targets:
        names.extend(target_names(target))
    return tuple(names)


def target_names(target: ast.AST) -> tuple[str, ...]:
    """Flatten names from a simple or tuple assignment target."""
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Tuple | ast.List):
        return tuple(name for item in target.elts for name in target_names(item))
    return ()


def call_name(node: ast.Call) -> str:
    """Return the dotted name of a call target."""
    return expression_name(node.func)


def expression_name(node: ast.AST) -> str:
    """Return a dotted symbolic expression name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ast.unparse(node)


def call_keyword(node: ast.Call, name: str) -> ast.AST | None:
    """Return one call keyword value."""
    return next(
        (keyword.value for keyword in node.keywords if keyword.arg == name),
        None,
    )


def _simple(node: ast.AST, environment: StaticEnvironment) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return environment.get(node.id, f"{{{node.id}}}")
    if isinstance(node, ast.JoinedStr):
        return _joined_string(node, environment)
    if isinstance(node, ast.Attribute):
        return _attribute(node, environment)
    if isinstance(node, ast.Subscript):
        return _subscript(node, environment)
    return _UNHANDLED


def _collection(node: ast.AST, environment: StaticEnvironment) -> object:
    if isinstance(node, ast.Dict):
        return _dictionary(node, environment)
    if isinstance(node, ast.List):
        return [evaluate(item, environment) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(evaluate(item, environment) for item in node.elts)
    if isinstance(node, ast.Set):
        return {str(evaluate(item, environment)) for item in node.elts}
    return _UNHANDLED


def _expression(node: ast.AST, environment: StaticEnvironment) -> object:
    if isinstance(node, ast.BinOp):
        result = _binary(node, environment)
    elif isinstance(node, ast.BoolOp):
        result = boolean_value(node, environment, evaluate)
    elif isinstance(node, ast.Compare):
        result = comparison_value(node, environment, evaluate)
    elif isinstance(node, ast.UnaryOp):
        result = _unary(node, environment)
    elif isinstance(node, ast.IfExp):
        decision = truth_value(node.test, environment)
        result = evaluate(
            node.orelse if decision is False else node.body,
            environment,
        )
    elif isinstance(node, ast.Call):
        result = _call(node, environment)
    else:
        result = _UNHANDLED
    return result


def _dictionary(
    node: ast.Dict,
    environment: StaticEnvironment,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        value = evaluate(value_node, environment)
        if key_node is None:
            if isinstance(value, Mapping):
                result.update({str(key): item for key, item in value.items()})
            continue
        result[str(evaluate(key_node, environment))] = value
    return result


def _joined_string(node: ast.JoinedStr, environment: StaticEnvironment) -> str:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif isinstance(value, ast.FormattedValue):
            parts.append(str(evaluate(value.value, environment)))
    return "".join(parts)


def _attribute(node: ast.Attribute, environment: StaticEnvironment) -> object:
    base = evaluate(node.value, environment)
    if node.attr == "value" and isinstance(base, str):
        return base.rsplit(".", maxsplit=1)[-1]
    if isinstance(base, Mapping):
        return base.get(node.attr, f"{{{node.attr}}}")
    return f"{base}.{node.attr}"


def _subscript(node: ast.Subscript, environment: StaticEnvironment) -> object:
    value = evaluate(node.value, environment)
    key = evaluate(node.slice, environment)
    try:
        return value[key]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return ast.unparse(node)


def _binary(node: ast.BinOp, environment: StaticEnvironment) -> object:
    left = evaluate(node.left, environment)
    right = evaluate(node.right, environment)
    operation = _BINARY_OPERATORS.get(type(node.op))
    if operation is None:
        return ast.unparse(node)
    try:
        return operation(left, right)
    except (TypeError, ValueError, ZeroDivisionError):
        return ast.unparse(node)


def _unary(node: ast.UnaryOp, environment: StaticEnvironment) -> object:
    value = evaluate(node.operand, environment)
    if isinstance(node.op, ast.USub) and isinstance(value, int | float):
        return -value
    if isinstance(node.op, ast.Not):
        return not bool(value)
    return ast.unparse(node)


def _call(node: ast.Call, environment: StaticEnvironment) -> object:
    name = call_name(node)
    args = [evaluate(argument, environment) for argument in node.args]
    kwargs = {
        str(keyword.arg): evaluate(keyword.value, environment)
        for keyword in node.keywords
        if keyword.arg is not None
    }
    special = constructor_value(name, args, kwargs)
    if special is not NOT_SPECIAL:
        return special
    builtin = _builtin_call(name, args, kwargs, node)
    if builtin is not _UNHANDLED:
        return builtin
    method = _method_call(name, node, args, kwargs, environment)
    if method is not _UNHANDLED:
        return method
    if "override_activity_args" in name or name.endswith("_with_activity_overrides"):
        return _merge_mappings(args)
    return ast.unparse(node)


def _builtin_call(
    name: str,
    args: list[object],
    kwargs: dict[str, object],
    node: ast.Call,
) -> object:
    if name in {"dict", "builtins.dict"}:
        return _dict_call(args, kwargs)
    if name in {"str", "builtins.str"} and args:
        return str(args[0])
    if name in {"int", "builtins.int"} and args:
        return _int_call(args[0], node)
    if name in {"set", "list"}:
        return _collection_call(name, args)
    return _UNHANDLED


def _int_call(value: object, node: ast.Call) -> object:
    if not isinstance(value, str | bytes | bytearray | int | float):
        return ast.unparse(node)
    try:
        return int(value)
    except (TypeError, ValueError):
        return ast.unparse(node)


def _collection_call(name: str, args: list[object]) -> object:
    value = args[0] if args else ()
    items = value if isinstance(value, Iterable) else ()
    if name == "set":
        return set(items)
    return list(items)


def _method_call(
    name: str,
    node: ast.Call,
    args: list[object],
    kwargs: dict[str, object],
    environment: StaticEnvironment,
) -> object:
    if not isinstance(node.func, ast.Attribute):
        return _UNHANDLED
    receiver = evaluate(node.func.value, environment)
    if isinstance(receiver, Mapping):
        special = method_value(receiver, node.func.attr, kwargs)
        if special is not NOT_SPECIAL:
            return special
    if name.endswith(".get") and isinstance(receiver, Mapping):
        default = args[1] if len(args) > 1 else None
        return receiver.get(args[0], default) if args else default
    if name.endswith(".format") and isinstance(receiver, str):
        try:
            return receiver.format(*args, **kwargs)
        except (KeyError, IndexError, ValueError):
            return receiver
    return _UNHANDLED


def _dict_call(
    args: list[object],
    kwargs: dict[str, object],
) -> dict[str, object]:
    result: dict[str, object] = {}
    if args and isinstance(args[0], Mapping):
        result.update({str(key): value for key, value in args[0].items()})
    result.update(kwargs)
    return result


def _merge_mappings(args: list[object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in args:
        if isinstance(value, Mapping):
            result.update({str(key): item for key, item in value.items()})
    return result
