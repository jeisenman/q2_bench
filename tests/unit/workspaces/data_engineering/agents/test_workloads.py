import pytest

from workspaces.data_engineering.agents.prod_support import (
    AirflowTaskMetadata,
    Region,
    WorkloadKind,
    classify_workload,
    route_oms_evidence,
)


@pytest.mark.parametrize(
    "operator_name",
    [
        "SparkSubmitOperator",
        "airflow.providers.apache.spark.operators.spark_submit.SparkSubmitOperator",
        "SparkKubernetesOperator",
        "DatabricksSubmitRunOperator",
    ],
)
def test_classifies_spark_operators(operator_name: str) -> None:
    metadata = AirflowTaskMetadata("dag", "task", operator_name)

    assert classify_workload(metadata) is WorkloadKind.SPARK_BATCH


@pytest.mark.parametrize(
    "operator_name",
    ["KubernetesPodOperator", "PythonOperator", "BashOperator"],
)
def test_classifies_non_spark_batch_operators(operator_name: str) -> None:
    metadata = AirflowTaskMetadata("dag", "task", operator_name)

    assert classify_workload(metadata) is WorkloadKind.CONTAINER_BATCH


def test_routes_only_spark_to_regional_oms() -> None:
    us_route = route_oms_evidence(WorkloadKind.SPARK_BATCH, Region.US_01)
    ca_route = route_oms_evidence(WorkloadKind.SPARK_BATCH, Region.CA_02)

    assert us_route is not None
    assert us_route.workspace_name == "pl-oms-us-primary"
    assert us_route.table == "DI_Scheduling_CL"
    assert ca_route is not None
    assert ca_route.workspace_name == "pl-oms-ca-primary"
    assert route_oms_evidence(WorkloadKind.CONTAINER_BATCH, Region.US_01) is None


@pytest.mark.parametrize("field", ["dag_id", "task_id", "operator_name"])
def test_rejects_incomplete_task_metadata(field: str) -> None:
    values = {
        "dag_id": "dag",
        "task_id": "task",
        "operator_name": "SparkSubmitOperator",
    }
    values[field] = ""

    with pytest.raises(ValueError, match=field):
        AirflowTaskMetadata(**values)
