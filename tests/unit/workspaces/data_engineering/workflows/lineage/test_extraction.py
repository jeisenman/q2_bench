from __future__ import annotations

import ast
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from workspaces.data_engineering.workflows.lineage.allocations import (
    AllocationIndex,
)
from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)
from workspaces.data_engineering.workflows.lineage.main_graph import (
    MainGraphScanner,
)
from workspaces.data_engineering.workflows.lineage.metadata import MetadataIndex
from workspaces.data_engineering.workflows.lineage.physical import (
    FunctionExtractionRequest,
    FunctionExtractor,
)
from workspaces.data_engineering.workflows.lineage.physical_dependencies import (
    assign_return_references,
    dependency_expression,
    reference_groups,
    references_for,
)
from workspaces.data_engineering.workflows.lineage.physical_support import (
    bind_arguments,
    is_task_function,
    operator_factory_call,
)
from workspaces.data_engineering.workflows.lineage.repository import (
    repository_manifest,
)
from workspaces.data_engineering.workflows.lineage.source import SourceIndex
from workspaces.data_engineering.workflows.lineage.workflow import (
    build_di_pipelines_graph,
    sync_di_pipelines_lineage,
)


class MemoryStore:
    def __init__(self) -> None:
        self.graph = None
        self.diff = None

    def latest(self, _repository: str, _profile: str):
        return self.graph

    def save(self, graph, graph_diff) -> bool:
        self.graph = graph
        self.diff = graph_diff
        return True


def test_metadata_inheritance_and_source_indexing(di_repository: Path) -> None:
    source = SourceIndex(di_repository)
    main = source.load_path(source.dag_root / "l3_main_graph.py")
    imported = source.resolve_function(main, "get_engagements")
    metadata = MetadataIndex.from_repository(di_repository)
    engagement = metadata.reference(
        "datascience_jobs.meta_data.datasets.engagements.EngagementMetadata"
    )

    assert source.module_name(main.path) == "l3_main_graph"
    assert source.module_name(di_repository / "dag-utils/operators.py") == (
        "utils.operators"
    )
    assert (
        source.module_name(
            di_repository
            / "ds-jobs/src/datascience_jobs/meta_data/datasets/engagements.py"
        )
        == "engagements"
    )
    assert source.module_path("unknown.module") is None
    assert source.load_module("unknown.module") is None
    assert imported is not None
    assert imported[1].name == "get_engagements"
    task_group = source.load_module("task_groups.main.engagements")
    assert task_group is not None
    assert isinstance(task_group.constants["ENGAGEMENT_ARGS"], dict)
    assert source.load_path(main.path) is main
    assert engagement is not None
    assert engagement.dataset == "PL_Andi/Engagement/PLChatEngagements"
    assert engagement.version == "v1.1"
    assert [field.name for field in engagement.fields] == ["id", "message"]
    assert engagement.fields[0].is_pii
    assert metadata.dataset(engagement.node_id) == engagement
    assert metadata.reference("missing.Metadata") is None

    missing_module_path = source.dag_root / "missing_module.py"
    missing_module_path.write_text(
        "from task_groups.missing import absent\n",
        encoding="utf-8",
    )
    missing_module = source.load_path(missing_module_path)
    assert source.resolve_function(missing_module, "absent") is None

    missing_function_path = source.dag_root / "missing_function.py"
    missing_function_path.write_text(
        "from task_groups.main.engagements import absent\n",
        encoding="utf-8",
    )
    missing_function = source.load_path(missing_function_path)
    assert source.resolve_function(missing_function, "absent") is None

    with pytest.raises(LineageValidationError, match="does not exist"):
        source.load_path(di_repository / "missing.py")


def test_physical_and_main_graph_scanners_follow_helpers_and_edges(
    di_repository: Path,
) -> None:
    source = SourceIndex(di_repository)
    intended = MainGraphScanner(source).scan()
    aggregate = next(item for item in intended.invocations if item.key == "aggregate")
    copies = next(item for item in intended.invocations if item.key == "copies")
    optional = next(item for item in intended.invocations if item.key == "optional")

    assert intended.dag_id == "l3_main_graph"
    assert {"start", "fallback", "grouped", "looped_{item}"}.issubset(
        {item.key for item in intended.invocations}
    )
    assert [job.name for job in aggregate.physical.jobs] == [
        "aggregate_pl_chat_engagements"
    ]
    assert {job.name for job in copies.physical.jobs} == {
        "aggregate_pl_chat_engagements",
        "pl_chat_engagements_to_internal_adls",
        "pl_chat_engagements_to_client_datamart_adls",
    }
    assert {job.name for job in optional.physical.jobs} == {
        "pl_chat_engagements_to_internal_adls",
        "pl_chat_engagements_to_client_datamart_adls",
    }
    assert ("start", "aggregate") in intended.dependencies
    assert ("aggregate", "copies") in intended.dependencies
    assert ("grouped", "fallback") in intended.dependencies


def test_full_workflow_condenses_copies_and_adds_snowflake(
    di_repository: Path,
) -> None:
    generated_at = datetime(2026, 10, 5, 12, tzinfo=UTC)
    graph = build_di_pipelines_graph(
        di_repository,
        generated_at=generated_at,
        source_ref="master",
    )
    semantic = next(
        item for item in graph.nodes if item.node_id.endswith("/plchatengagements")
    )
    snowflake = next(
        item
        for item in graph.nodes
        if item.node_id.endswith("/client_data_mart.pl_chat_engagements")
    )
    names = {item.name for item in semantic.transformations}

    assert graph.manifest.repository == "precisionlender/di-pipelines"
    assert graph.manifest.generated_at == generated_at
    assert names >= {
        "aggregate_pl_chat_engagements",
        "pl_chat_engagements_to_internal_adls",
        "pl_chat_engagements_to_client_datamart_adls",
    }
    assert {location.resource for location in semantic.locations} >= {
        "HistoricalDataMartADLS",
        "InternalDataMartADLS",
        "ClientDataMartADLS",
    }
    assert [field.name for field in snowflake.fields] == ["id", "message"]
    assert semantic.context is not None
    assert semantic.context.derived
    assert any(
        edge.source_id == semantic.node_id
        and edge.target_id.endswith(
            "/snowflake_ingestion/pl_andi_engagement_plchatengagements"
        )
        for edge in graph.edges
    )
    aggregate = next(
        item
        for item in semantic.transformations
        if item.name == "aggregate_pl_chat_engagements"
    )
    assert aggregate.allocation is not None
    assert aggregate.allocation.standard.compute == "batch"
    assert len(aggregate.allocation.larger_clients) == 1
    larger = aggregate.allocation.larger_clients[0]
    assert larger.client_name == "Bigger Bank"
    assert larger.resource_size == "large"
    assert larger.allocation.compute == "k8s_pod"
    assert dict(larger.allocation.container_resources)["limits.memory"] == "16Gi"
    spark_copy = next(
        item
        for item in semantic.transformations
        if item.name == "pl_chat_engagements_to_internal_adls"
    )
    assert spark_copy.allocation is not None
    assert dict(spark_copy.allocation.standard.spark_variables) == {
        "driver_cores": "2",
        "driver_max_result_size": "2g",
        "driver_memory": "4g",
        "executor_cores": "4",
        "executor_instances_max": "30",
        "executor_instances_min": "3",
        "executor_memory": "16g",
    }

    store = MemoryStore()
    first = sync_di_pipelines_lineage(
        di_repository,
        store,
        generated_at=generated_at,
        source_ref="master",
    )
    second = sync_di_pipelines_lineage(
        di_repository,
        store,
        generated_at=generated_at,
        source_ref="master",
    )
    assert first.inserted
    assert first.diff.changed
    assert second.inserted
    assert not second.diff.changed
    assert first.graph.manifest.graph_id == second.graph.manifest.graph_id


def test_allocation_index_falls_back_for_jobs_outside_the_main_graph(
    di_repository: Path,
) -> None:
    source = SourceIndex(di_repository)
    allocations = AllocationIndex.from_repository(source)
    module = source.load_path(source.dag_root / "snowflake_ingestion.py")
    extraction = FunctionExtractor(source).extract(
        module,
        module.functions["build_snowflake_ingestion_dag"],
        FunctionExtractionRequest(
            ("spark", {"group"}, {"shared"}),
            {},
            "snowflake_ingestion",
        ),
    )

    policy = allocations.job(extraction.jobs[0])

    assert policy.standard.compute == "snowflake"
    assert not policy.larger_clients


def test_repository_manifest_supports_local_and_detached_repositories(
    di_repository: Path,
) -> None:
    at = datetime(2026, 10, 5, tzinfo=UTC)
    first = repository_manifest(di_repository, generated_at=at)
    second = repository_manifest(di_repository, generated_at=at)
    subprocess.run(
        ("git", "-C", str(di_repository), "remote", "remove", "origin"),
        check=True,
    )
    local = repository_manifest(di_repository, generated_at=at, source_ref="HEAD")

    assert first.graph_id == second.graph_id
    assert first.source_ref == "master"
    assert local.repository == "di-pipelines"
    assert local.source_ref == "HEAD"

    with pytest.raises(LineageValidationError, match="unable to inspect"):
        repository_manifest(di_repository / "missing")


def test_physical_helpers_cover_binding_recursion_and_dependency_shapes(
    di_repository: Path,
) -> None:
    source = SourceIndex(di_repository)
    module = source.load_module("task_groups.main.engagements")
    assert module is not None
    function = module.functions["get_engagements"]
    bound = bind_arguments(function, ("client",), {}, module)
    extraction = FunctionExtractor(source).extract(
        module,
        function,
        FunctionExtractionRequest(("client",), {}, "test"),
    )

    assert bound == {"client": "client", "suffix": ""}
    assert is_task_function(function)
    assert not is_task_function(ast.parse("def plain():\n    return 1\n").body[0])
    assert extraction.returns
    assert operator_factory_call(ast.parse("value()", mode="eval").body) is None

    references = {"a": ("job-a",), "b": ("job-b",), "both": ("job-a", "job-b")}
    assert references_for(ast.parse("[a, b]", mode="eval").body, references) == (
        "job-a",
        "job-b",
    )
    assert reference_groups(None, references) == ()
    assert reference_groups(ast.parse("both", mode="eval").body, references) == (
        ("job-a", "job-b"),
    )
    assigned: dict[str, tuple[str, ...]] = {}
    assign_return_references(("one",), (("a",), ("b",)), assigned)
    assert assigned["one"] == ("a", "b")
    assign_return_references(("left", "right"), (("a",), ("b",)), assigned)
    assert assigned["right"] == ("b",)

    dependencies: set[tuple[str, str]] = set()
    dependency_expression(
        ast.parse("a >> b << both", mode="eval").body,  # type: ignore[arg-type]
        references,
        dependencies,
    )
    assert ("job-a", "job-b") in dependencies
