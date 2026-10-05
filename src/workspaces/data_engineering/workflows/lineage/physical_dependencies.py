"""Reference and dependency helpers for static Airflow expressions."""

from __future__ import annotations

import ast


def assign_return_references(
    names: tuple[str, ...],
    groups: tuple[tuple[str, ...], ...],
    references: dict[str, tuple[str, ...]],
) -> None:
    """Bind returned physical tasks to caller variables."""
    if len(names) == 1:
        references[names[0]] = tuple(item for group in groups for item in group)
        return
    references.update(zip(names, groups, strict=False))


def reference_groups(
    expression: ast.AST | None,
    references: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], ...]:
    """Return physical task groups represented by a return expression."""
    if expression is None:
        return ()
    if isinstance(expression, ast.Tuple | ast.List):
        return tuple(references_for(item, references) for item in expression.elts)
    return (references_for(expression, references),)


def references_for(
    expression: ast.AST,
    references: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Resolve physical tasks represented by one expression."""
    if isinstance(expression, ast.Name):
        return references.get(expression.id, ())
    if isinstance(expression, ast.List | ast.Tuple):
        return tuple(
            item
            for value in expression.elts
            for item in references_for(value, references)
        )
    return ()


def dependency_expression(
    expression: ast.BinOp,
    references: dict[str, tuple[str, ...]],
    dependencies: set[tuple[str, str]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Record Airflow shift-operator dependencies."""
    left_first, left_last = _dependency_side(
        expression.left,
        references,
        dependencies,
    )
    right_first, right_last = _dependency_side(
        expression.right,
        references,
        dependencies,
    )
    if isinstance(expression.op, ast.RShift):
        dependencies.update(
            (source, target) for source in left_last for target in right_first
        )
        return left_first, right_last
    if isinstance(expression.op, ast.LShift):
        dependencies.update(
            (source, target) for source in right_last for target in left_first
        )
        return right_first, left_last
    return left_first, right_last


def _dependency_side(
    expression: ast.AST,
    references: dict[str, tuple[str, ...]],
    dependencies: set[tuple[str, str]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if isinstance(expression, ast.BinOp):
        return dependency_expression(expression, references, dependencies)
    found = references_for(expression, references)
    return found, found
