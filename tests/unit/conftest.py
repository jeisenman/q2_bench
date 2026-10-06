from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from radar_fixtures import create_radar_repositories

from workspaces.data_engineering.workflows.lineage import RadarRepositories


@pytest.fixture
def di_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "di-pipelines"
    _write(
        repository / "dags/precisionlender/dags/l3_main_graph.py",
        """
from task_groups.main.engagements import get_engagements, get_returned

def build_abstract_dag():
    start = EmptyOperator(task_id="start")
    aggregate, copies = get_engagements(client)
    if feature_enabled:
        optional = get_returned()
    else:
        fallback = EmptyOperator(task_id="fallback")
    with task_group:
        grouped = EmptyOperator(task_id="grouped")
    for item in ["one"]:
        looped = EmptyOperator(task_id=f"looped_{item}")
    start >> aggregate >> copies
    fallback << grouped
""",
    )
    _write(
        repository / "dags/precisionlender/dags/task_groups/main/engagements.py",
        """
from utils.resource_allocation import ENGAGEMENT_ARGS

METADATA = (
    "datascience_jobs.meta_data.datasets.engagements.EngagementMetadata"
)

def dataset_with_activity_overrides(base, overrides):
    return {**base, **overrides}

def _get_copy_tasks():
    internal = OperatorFactory(
        job_name="pl_chat_engagements_to_internal_adls",
        job_reference="CopyDatasetJob",
        override_activity_args=dataset_with_activity_overrides(
            {
                "targetDatasetMetadata": METADATA,
                "outputPathConvention": "client/{clientId}",
            },
            {"outputResource": "InternalDataMartADLS"},
        ),
    ).operate(compute="spark")
    client_copy = OperatorFactory(
        job_name="pl_chat_engagements_to_client_datamart_adls",
        job_reference="CopyDatasetJob",
        override_activity_args=dataset_with_activity_overrides(
            {
                "targetDatasetMetadata": METADATA,
                "outputPathConvention": "client/{clientId}",
                "raFile": "DatabaseOutput/dbStagingRelationshipNew.csv",
            },
            {"outputResource": "ClientDataMartADLS"},
        ),
    ).operate(compute="spark")
    return internal, client_copy

def _get_side_effect():
    side_effect = OperatorFactory(
        job_name="audit_engagements",
        job_reference="AuditJob",
        override_activity_args=dataset_with_activity_overrides(
            {"targetDatasetMetadata": METADATA},
            {"outputResource": "AuditADLS"},
        ),
    ).operate(compute="small")
    return side_effect

def get_engagements(client, suffix=""):
    aggregate = OperatorFactory(
        job_name="aggregate_pl_chat_engagements",
        job_reference="AggregatePLChatEngagementsJob",
        override_operator_args=ENGAGEMENT_ARGS.args(
            client_id=client["clientId"],
        ),
        override_activity_args=dataset_with_activity_overrides(
            {
                "targetDatasetMetadata": METADATA,
                "outputPathConvention": "client/{clientId}",
            },
            {"outputResource": "HistoricalDataMartADLS"},
        ),
    ).operate(compute=ENGAGEMENT_ARGS.compute(client_id=client["clientId"]))
    internal, client_copy = _get_copy_tasks()
    if client:
        _get_side_effect()
    try:
        aggregate >> [internal, client_copy]
    except RuntimeError:
        pass
    return aggregate, [internal, client_copy]

def get_returned():
    return _get_copy_tasks()
""",
    )
    _write(
        repository / "dag-utils/operators.py",
        """
from kubernetes.client.models.v1_resource_requirements import (
    V1ResourceRequirements,
)

DEFAULT_POD_JOB_RESOURCES = V1ResourceRequirements(
    limits={"cpu": "2000m", "memory": "4Gi"},
    requests={"cpu": "2000m", "memory": "4Gi"},
)
MEMORY_LG_RESOURCES = V1ResourceRequirements(
    limits={"cpu": "2000m", "memory": "16Gi"},
    requests={"cpu": "2000m", "memory": "16Gi"},
)

class SparkSubmitOperatorBuilder:
    @property
    def default_spark_conf_template_variables(self):
        return dict(
            driver_cores="2",
            driver_memory="4g",
            driver_max_result_size="2g",
            executor_instances_min="3",
            executor_instances_max="30",
            executor_cores="4",
            executor_memory="16g",
        )
""",
    )
    larger_client_id = "11111111-1111-4111-8111-111111111111"
    _write(
        repository / "dag-utils/resource_allocation.py",
        f"""
from utils.operators import MEMORY_LG_RESOURCES

ENGAGEMENT_ARGS = ClientArgOverrides(
    default={{}},
    client_overrides={{
        "{larger_client_id}": {{
            "container_resources": MEMORY_LG_RESOURCES,
        }},
    }},
    backfill_overrides={{}},
)
""",
    )
    _write(
        repository
        / "de-jobs/src/datamart/jobs/cross_client/clients_metadata_airflow.py",
        f"""
CLIENT_RESOURCE_TAGS = {{
    "{larger_client_id}": {{"size": "large"}},  # Bigger Bank
}}
""",
    )
    _write(
        repository / "dags/precisionlender/dags/snowflake_ingestion.py",
        """
METADATA = (
    "datascience_jobs.meta_data.datasets.engagements.EngagementMetadata"
)

def build_snowflake_ingestion_dag(
    spark_resource_group,
    mi_groups,
    shared_resource_groups,
):
    for group in mi_groups:
        load = OperatorFactory(
            job_name=f"load_{group}",
            job_reference="SnowflakeIngestionJob",
            override_activity_args={"targetDatasetMetadata": METADATA},
        ).operate(compute="snowflake")
    return load
""",
    )
    metadata_root = repository / "ds-jobs/src/datascience_jobs/meta_data/datasets"
    _write(
        metadata_root / "base.py",
        """
class BaseMetadata:
    PATH_STAGE = "Primary"
    PATH_PROVIDER = "PL_Andi"
    PATH_GROUP = "Engagement"
    LATEST_MAJOR_VERSION = 1
    LATEST_MINOR_VERSION = 0
    DATASET_DESCRIPTION = "Engagement records."

    def _v1_0_fields(self):
        return [
            DatasetField(
                "id",
                StringType(),
                False,
                definition="Engagement identifier.",
                is_pii=True,
            )
        ]
""",
    )
    _write(
        metadata_root / "engagements.py",
        """
from datascience_jobs.meta_data.datasets.base import BaseMetadata

class EngagementMetadata(BaseMetadata):
    DATASET_NAME = "PLChatEngagements"
    LATEST_MINOR_VERSION = 1
    SNOWFLAKE_SCHEMA = "Client_Data_Mart"
    SNOWFLAKE_TABLE = "PL_CHAT_ENGAGEMENTS"

    def _v1_1_fields(self):
        return [
            DatasetField(
                name="message",
                dataType=StringType(),
                nullable=True,
                definition="Chat message.",
            )
        ]
""",
    )
    _git(repository, "init", "-b", "master")
    _git(repository, "config", "user.email", "lineage@example.com")
    _git(repository, "config", "user.name", "Lineage Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "fixture")
    _git(
        repository,
        "remote",
        "add",
        "origin",
        "git@github.com:precisionlender/di-pipelines.git",
    )
    return repository


@pytest.fixture
def radar_repositories(
    tmp_path: Path,
    di_repository: Path,
) -> RadarRepositories:
    return create_radar_repositories(tmp_path, di_repository)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
