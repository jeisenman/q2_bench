"""Classify Airflow task metadata and select an OMS evidence route."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from workspaces.data_engineering.agents.oms_agent import (
    OMS_TABLE,
    OmsEnvironment,
    OmsRegion,
    resolve_workspace,
)
from workspaces.data_engineering.agents.production_support.models import Region

SPARK_OPERATORS = frozenset(
    {
        "DatabricksRunNowOperator",
        "DatabricksSubmitRunOperator",
        "SparkKubernetesOperator",
        "SparkSubmitOperator",
    }
)
CONTAINER_BATCH_OPERATORS = frozenset(
    {
        "BashOperator",
        "KubernetesPodOperator",
        "PythonOperator",
    }
)


class AirflowTaskMetadataError(ValueError):
    """Raised when Airflow task metadata is incomplete."""

    @classmethod
    def empty_field(cls, label: str) -> AirflowTaskMetadataError:
        """Return an error for one missing task metadata field."""
        return cls(f"{label} must not be empty")


class WorkloadKind(StrEnum):
    """Supported Airflow workload categories."""

    SPARK_BATCH = "spark_batch"
    CONTAINER_BATCH = "container_batch"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class AirflowTaskMetadata:
    """Task metadata returned by the Airflow task endpoint."""

    dag_id: str
    task_id: str
    operator_name: str

    def __post_init__(self) -> None:
        """Reject incomplete metadata at the Airflow boundary."""
        for value, label in (
            (self.dag_id, "dag_id"),
            (self.task_id, "task_id"),
            (self.operator_name, "operator_name"),
        ):
            if not value.strip():
                raise AirflowTaskMetadataError.empty_field(label)


@dataclass(frozen=True, slots=True)
class OmsEvidenceRoute:
    """Regional OMS destination for a supported workload."""

    workspace_name: str
    table: str


def classify_workload(metadata: AirflowTaskMetadata) -> WorkloadKind:
    """Classify workload type from the exact Airflow operator class."""
    operator_name = metadata.operator_name.rsplit(".", maxsplit=1)[-1]
    if operator_name in SPARK_OPERATORS:
        return WorkloadKind.SPARK_BATCH
    if operator_name in CONTAINER_BATCH_OPERATORS:
        return WorkloadKind.CONTAINER_BATCH
    return WorkloadKind.OTHER


def route_oms_evidence(
    workload: WorkloadKind,
    region: Region,
) -> OmsEvidenceRoute | None:
    """Route confirmed Spark jobs to OMS; keep other workloads in Airflow."""
    if workload is not WorkloadKind.SPARK_BATCH:
        return None
    oms_region = {
        Region.US_01: OmsRegion.US,
        Region.CA_02: OmsRegion.CA,
    }[region]
    workspace = resolve_workspace(OmsEnvironment.PRODUCTION, oms_region)
    return OmsEvidenceRoute(workspace_name=workspace.name, table=OMS_TABLE)
