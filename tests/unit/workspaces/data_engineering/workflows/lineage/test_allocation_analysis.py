from __future__ import annotations

import ast
from pathlib import Path

from workspaces.data_engineering.workflows.lineage import (
    JobAllocation,
    ResourceAllocation,
)
from workspaces.data_engineering.workflows.lineage.ast_allocation_values import (
    NOT_SPECIAL,
    constructor_value,
    mapping_object,
    method_value,
)
from workspaces.data_engineering.workflows.lineage.ast_values import evaluate
from workspaces.data_engineering.workflows.lineage.operator_defaults import (
    operator_defaults,
)
from workspaces.data_engineering.workflows.lineage.physical_allocation import (
    resource_allocation,
)

EXPECTED_BOOLEAN_VALUE = 3


def expression(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


def test_allocation_value_helpers_cover_defaults_backfills_and_unknowns() -> None:
    resources = constructor_value(
        "V1ResourceRequirements",
        [],
        {"limits": {"memory": "16Gi"}},
    )
    client_args = constructor_value(
        "ClientArgOverrides",
        [
            {"retries": 1},
            {"large-client": {"container_resources": resources}},
            {"retries": 3},
        ],
        {},
    )
    spark = constructor_value(
        "ClientSparkConfOverrides",
        [],
        {
            "default": {"spark.executor.instances": "3"},
            "client_overrides": {"large-client": {"spark.executor.instances": "10"}},
            "backfill_overrides": {"spark.executor.instances": "20"},
        },
    )

    assert isinstance(client_args, dict)
    assert isinstance(spark, dict)
    assert method_value(client_args, "compute", {}) == "batch"
    assert (
        method_value(client_args, "compute", {"client_id": "large-client"}) == "k8s_pod"
    )
    assert method_value(client_args, "args", {"backfill": True}) == {"retries": 3}
    assert method_value(spark, "spark_conf", {"client_id": "large-client"}) == {
        "spark.executor.instances": "10"
    }
    assert method_value(spark, "spark_conf", {"backfill": True}) == {
        "spark.executor.instances": "20"
    }
    assert method_value({}, "args", {}) is NOT_SPECIAL
    assert method_value(client_args, "unknown", {}) is NOT_SPECIAL
    assert constructor_value("Unknown", [], {}) is NOT_SPECIAL
    assert mapping_object("not-a-mapping") == {}


def test_condition_evaluation_covers_boolean_and_comparison_operators() -> None:
    environment = {"a": 2, "b": 3, "items": {2, 4}, "truthy": "value"}

    assert evaluate(expression("False or truthy"), environment) == "value"
    assert evaluate(expression("True and b"), environment) == EXPECTED_BOOLEAN_VALUE
    assert evaluate(expression("unknown or True"), environment) == "unknown or True"
    assert evaluate(expression("a != b"), environment)
    assert evaluate(expression("a not in {1, 3}"), environment)
    assert evaluate(expression("a < b <= 3"), environment)
    assert evaluate(expression("b > a >= 2"), environment)
    assert evaluate(expression("a is not b"), environment)
    assert evaluate(expression("a in items"), environment)
    assert evaluate(expression("a < 'invalid'"), environment) is False


def test_operator_defaults_handles_missing_and_unrecognized_framework(
    tmp_path: Path,
) -> None:
    assert operator_defaults(tmp_path) == operator_defaults(tmp_path)
    operators = tmp_path / "with-operators" / "dag-utils" / "operators.py"
    operators.parent.mkdir(parents=True)
    operators.write_text(
        """
class Other:
    pass

class SparkSubmitOperatorBuilder:
    ignored = 1

    def other_method(self):
        return {}

    @property
    def default_spark_conf_template_variables(self):
        return "not-a-mapping"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    defaults = operator_defaults(tmp_path / "with-operators")

    assert defaults.pod_resources is None
    assert not defaults.spark_variables


def test_allocation_deserialization_handles_partial_external_payloads() -> None:
    policy = JobAllocation.from_dict(
        {
            "standard": {"compute": "batch", "containerResources": "invalid"},
            "largerClients": "invalid",
        }
    )

    assert policy == JobAllocation(ResourceAllocation("batch"))


def test_physical_allocation_applies_pod_defaults_and_expanded_arguments(
    di_repository: Path,
) -> None:
    plain_call = expression("OperatorFactory()")
    expanded_call = expression("OperatorFactory(**options)")
    assert isinstance(plain_call, ast.Call)
    assert isinstance(expanded_call, ast.Call)

    pod = resource_allocation(plain_call, "k8s_pod", {}, di_repository)
    spark = resource_allocation(
        expanded_call,
        "spark",
        {
            "options": {
                "override_spark_conf_template_variables": {
                    "executor_instances_max": "50"
                }
            }
        },
        di_repository,
    )
    batch = resource_allocation(
        expanded_call,
        "batch",
        {
            "options": {
                "override_spark_conf_template": {"spark.executor.cores": "8"},
                "override_spark_conf_template_variables": {
                    "executor_instances_max": "50"
                },
            }
        },
        di_repository,
    )

    assert dict(pod.container_resources)["limits.memory"] == "4Gi"
    assert dict(spark.spark_variables)["executor_instances_max"] == "50"
    assert not batch.spark_configuration
    assert not batch.spark_variables
