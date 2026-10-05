from __future__ import annotations

import ast

from workspaces.data_engineering.workflows.lineage.ast_values import (
    assignment_names,
    call_keyword,
    call_name,
    evaluate,
    expression_name,
    mapping_value,
    module_constants,
    stringify,
    target_names,
    truth_value,
)

EXPECTED_SUM = 3
EXPECTED_QUOTIENT = 2
EXPECTED_NEGATIVE = -4
EXPECTED_INTEGER = 4


def expression(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


def test_safe_static_evaluation_handles_source_metadata_patterns() -> None:
    environment = {
        "client": {"id": "abc", "size": 4},
        "enum": "Stage.Primary",
        "items": ("a", "b"),
    }

    assert evaluate(expression("f\"client-{client['id']}\""), environment) == (
        "client-abc"
    )
    assert evaluate(expression("client.id"), environment) == "abc"
    assert evaluate(expression("enum.value"), environment) == "Primary"
    assert evaluate(expression("client['missing']"), environment) == (
        "client['missing']"
    )
    assert evaluate(expression("{'a': 1, **client}"), environment)["id"] == "abc"  # type: ignore[index]
    assert evaluate(expression("[1, 2]"), environment) == [1, 2]
    assert evaluate(expression("(1, 2)"), environment) == (1, 2)
    assert evaluate(expression("{'a', 'b'}"), environment) == {"a", "b"}
    assert evaluate(expression("1 + 2"), environment) == EXPECTED_SUM
    assert evaluate(expression("5 // 2"), environment) == EXPECTED_QUOTIENT
    assert evaluate(expression("1 / 0"), environment) == "1 / 0"
    assert evaluate(expression("-4"), environment) == EXPECTED_NEGATIVE
    assert evaluate(expression("not items"), environment) is False
    assert evaluate(expression("1 if unknown else 2"), environment) == 1


def test_call_evaluation_handles_builtins_methods_and_activity_merges() -> None:
    environment = {"mapping": {"key": "value"}, "items": ("a", "b")}

    assert evaluate(expression("dict(mapping, added=2)"), environment) == {
        "key": "value",
        "added": 2,
    }
    assert evaluate(expression("str(3)"), environment) == "3"
    assert evaluate(expression("int('4')"), environment) == EXPECTED_INTEGER
    assert evaluate(expression("int('bad')"), environment) == "int('bad')"
    assert evaluate(expression("set(items)"), environment) == {"a", "b"}
    assert evaluate(expression("list(items)"), environment) == ["a", "b"]
    assert evaluate(expression("mapping.get('missing', 'fallback')"), environment) == (
        "fallback"
    )
    assert evaluate(expression("'{}-{}'.format('a', 'b')"), environment) == "a-b"
    assert evaluate(
        expression("override_activity_args({'a': 1}, {'b': 2})"),
        environment,
    ) == {"a": 1, "b": 2}
    assert mapping_value(expression("'not-a-map'"), environment) == {}
    assert stringify({"a": 1}) == "{'a': 1}"
    assert stringify(None) == ""


def test_allocation_helpers_and_conditions_resolve_client_profiles() -> None:
    resources = evaluate(
        expression(
            "V1ResourceRequirements("
            "limits={'cpu': '2', 'memory': '16Gi'}, "
            "requests={'cpu': '2', 'memory': '16Gi'})"
        ),
        {},
    )
    overrides = evaluate(
        expression(
            "ClientArgOverrides("
            "default={}, "
            "client_overrides={'client-a': {'container_resources': resources}}, "
            "backfill_overrides={})"
        ),
        {"resources": resources},
    )
    environment = {
        "client_id": "client-a",
        "resource_size": "large",
        "overrides": overrides,
    }

    assert truth_value(
        expression("client_id == 'client-a' and resource_size in {'large', 'xlarge'}"),
        environment,
    )
    assert (
        evaluate(
            expression("overrides.compute(client_id=client_id)"),
            environment,
        )
        == "k8s_pod"
    )
    assert isinstance(
        evaluate(
            expression("overrides.args(client_id=client_id)"),
            environment,
        ),
        dict,
    )
    assert truth_value(expression("unknown == 'value'"), environment) is None


def test_ast_name_and_constant_helpers_cover_assignment_shapes() -> None:
    tree = ast.parse(
        """
A = 1
B: int = A + 2
C, D = ("c", "d")
"""
    )
    constants = module_constants(tree)
    assignment = tree.body[-1]
    call = expression("factory(value=1)")
    assert isinstance(assignment, ast.Assign)
    assert isinstance(call, ast.Call)

    assert constants == {"A": 1, "B": 3, "C": ("c", "d"), "D": ("c", "d")}
    assert assignment_names(assignment) == ("C", "D")
    assert target_names(expression("obj.value")) == ()
    assert call_name(call) == "factory"
    assert expression_name(expression("module.factory")) == "module.factory"
    assert call_keyword(call, "value") is not None
    assert call_keyword(call, "missing") is None
