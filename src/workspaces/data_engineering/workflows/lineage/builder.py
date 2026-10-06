"""Build semantic OpenLineage entities from DI Pipelines source evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from workspaces.data_engineering.workflows.lineage.allocations import (
    AllocationIndex,
)
from workspaces.data_engineering.workflows.lineage.enrichments import (
    SourceLocation,
)
from workspaces.data_engineering.workflows.lineage.graph_models import (
    LineageGraph,
    RepositoryManifest,
)
from workspaces.data_engineering.workflows.lineage.identifiers import (
    airflow_job_identifier,
    dataset_identifier,
    snowflake_dataset_identifier,
)
from workspaces.data_engineering.workflows.lineage.main_graph import IntendedDag
from workspaces.data_engineering.workflows.lineage.metadata import (
    DatasetMetadata,
    MetadataIndex,
)
from workspaces.data_engineering.workflows.lineage.models import (
    CanonicalIdentifier,
    DatasetField,
    DatasetLocation,
    DerivedContext,
    EdgeKind,
    LineageEdge,
    LineageNode,
    Transformation,
)
from workspaces.data_engineering.workflows.lineage.physical import (
    FunctionExtractionRequest,
    FunctionExtractor,
    PhysicalExtraction,
    PhysicalJob,
)
from workspaces.data_engineering.workflows.lineage.source import SourceIndex

CONTEXT_GENERATOR = "q2-lineage-static-context-v1"


@dataclass(slots=True)
class _NodeParts:
    identifier: CanonicalIdentifier
    description: str | None = None
    versions: set[str] = field(default_factory=set)
    fields: dict[str, DatasetField] = field(default_factory=dict)
    locations: set[DatasetLocation] = field(default_factory=set)
    transformations: dict[str, Transformation] = field(default_factory=dict)
    sources: set[SourceLocation] = field(default_factory=set)
    owners: set[str] = field(default_factory=set)
    attributes: dict[str, str] = field(default_factory=dict)

    def build(self) -> LineageNode:
        """Freeze accumulated node evidence."""
        version = ",".join(sorted(self.versions)) or None
        context = _context(self)
        return LineageNode(
            identifier=self.identifier,
            description=self.description,
            version=version,
            fields=tuple(self.fields.values()),
            locations=tuple(
                sorted(
                    self.locations,
                    key=lambda item: (
                        item.resource,
                        item.path_convention or "",
                        item.role,
                    ),
                )
            ),
            transformations=tuple(
                sorted(
                    self.transformations.values(),
                    key=lambda item: (item.name, item.source.path, item.source.line),
                )
            ),
            sources=tuple(
                sorted(self.sources, key=lambda item: (item.path, item.line))
            ),
            owners=tuple(sorted(self.owners)),
            context=context,
            attributes=tuple(sorted(self.attributes.items())),
        )


class DiPipelinesGraphBuilder:
    """Construct the intended main and Snowflake ingestion graph."""

    def __init__(
        self,
        index: SourceIndex,
        metadata: MetadataIndex,
        allocations: AllocationIndex,
    ) -> None:
        """Initialize source and metadata indexes."""
        self._index = index
        self._metadata = metadata
        self._allocations = allocations
        self._nodes: dict[str, _NodeParts] = {}
        self._edges: dict[str, LineageEdge] = {}
        self._outputs: dict[str, set[str]] = defaultdict(set)

    def build(
        self,
        manifest: RepositoryManifest,
        intended: IntendedDag,
    ) -> LineageGraph:
        """Build a deterministic graph for one repository revision."""
        self._add_main_graph(intended)
        self._add_snowflake_ingestion()
        nodes = tuple(
            sorted(
                (parts.build() for parts in self._nodes.values()),
                key=lambda item: item.node_id,
            )
        )
        edges = tuple(sorted(self._edges.values(), key=lambda item: item.edge_id))
        return LineageGraph(manifest, nodes, edges)

    def _add_main_graph(self, intended: IntendedDag) -> None:
        for invocation in intended.invocations:
            identifier = airflow_job_identifier(intended.dag_id, invocation.key)
            parts = self._node(identifier)
            parts.description = (
                f"Runs the {invocation.function} task group from the L3 main graph."
            )
            parts.sources.add(invocation.source)
            parts.attributes["function"] = invocation.function
            parts.attributes["control"] = str(invocation.control).lower()
            for job in invocation.physical.jobs:
                parts.transformations[job.key] = self._transformation(job)
                parts.sources.add(job.source)
            datasets = self._datasets_from_physical(invocation.physical)
            for dataset_id in datasets:
                self._outputs[invocation.key].add(dataset_id)
                self._edge(identifier.value, dataset_id, EdgeKind.PRODUCES)

        for upstream, downstream in intended.dependencies:
            source = airflow_job_identifier(intended.dag_id, upstream).value
            target = airflow_job_identifier(intended.dag_id, downstream).value
            if source not in self._nodes or target not in self._nodes:
                continue
            self._edge(source, target, EdgeKind.DEPENDS_ON)
            for dataset_id in self._outputs[upstream]:
                self._edge(
                    dataset_id,
                    target,
                    EdgeKind.CONSUMES,
                    (("inference", "task_group_dependency"),),
                )

    def _datasets_from_physical(
        self,
        extraction: PhysicalExtraction,
    ) -> set[str]:
        jobs_by_key = {job.key: job for job in extraction.jobs}
        identities: dict[str, set[str]] = defaultdict(set)
        for job in extraction.jobs:
            dataset = _dataset_from_activity(job, self._metadata)
            if dataset is not None:
                identities[dataset.node_id].add(job.key)
        result: set[str] = set()
        for node_id, direct_keys in identities.items():
            sample = next(
                job
                for job in extraction.jobs
                if job.key in direct_keys
                and _dataset_from_activity(job, self._metadata).node_id == node_id  # type: ignore[union-attr]
            )
            metadata = self._metadata.dataset(node_id)
            transformations = _related_jobs(
                direct_keys,
                extraction.dependencies,
                jobs_by_key,
            )
            self._add_logical_dataset(sample, metadata, transformations)
            result.add(node_id)
        return result

    def _add_logical_dataset(
        self,
        sample: PhysicalJob,
        metadata: DatasetMetadata | None,
        transformations: tuple[PhysicalJob, ...],
    ) -> None:
        activity = sample.activity_mapping
        stage = metadata.stage if metadata else activity.get("datasetStage", "Unknown")
        dataset = metadata.dataset if metadata else activity["dataset"]
        identifier = dataset_identifier(stage, dataset)
        parts = self._node(identifier)
        version = metadata.version if metadata else activity.get("datasetVersion")
        if version:
            parts.versions.add(version)
        if metadata:
            _apply_metadata(parts, metadata)
        for job in transformations:
            parts.transformations[job.key] = self._transformation(job)
            parts.sources.add(job.source)
            location = _output_location(job)
            if location:
                parts.locations.add(location)

    def _add_snowflake_ingestion(self) -> None:
        path = self._index.dag_root / "snowflake_ingestion.py"
        module = self._index.load_path(path, name="snowflake_ingestion")
        function = module.functions["build_snowflake_ingestion_dag"]
        extraction = FunctionExtractor(self._index).extract(
            module,
            function,
            _snowflake_request(),
        )
        by_metadata: dict[str, list[PhysicalJob]] = defaultdict(list)
        for job in extraction.jobs:
            reference = job.activity_mapping.get("targetDatasetMetadata")
            if reference:
                by_metadata[reference].append(job)
        for reference, jobs in sorted(by_metadata.items()):
            metadata = self._metadata.reference(reference)
            if metadata is None:
                continue
            source_identifier = dataset_identifier(metadata.stage, metadata.dataset)
            source = self._node(source_identifier)
            _apply_metadata(source, metadata)
            job_identifier = airflow_job_identifier(
                "snowflake_ingestion",
                metadata.dataset,
            )
            job_parts = self._node(job_identifier)
            job_parts.description = (
                f"Loads {metadata.dataset} into its final Snowflake table."
            )
            for job in jobs:
                job_parts.transformations[job.key] = self._transformation(job)
                job_parts.sources.add(job.source)
            if not metadata.snowflake_schema or not metadata.snowflake_table:
                continue
            destination_identifier = snowflake_dataset_identifier(
                metadata.snowflake_schema,
                metadata.snowflake_table,
            )
            destination = self._node(destination_identifier)
            _apply_metadata(destination, metadata)
            destination.locations.add(
                DatasetLocation(
                    f"Snowflake.{metadata.snowflake_schema}.{metadata.snowflake_table}"
                )
            )
            self._edge(
                source_identifier.value,
                job_identifier.value,
                EdgeKind.CONSUMES,
            )
            self._edge(
                job_identifier.value,
                destination_identifier.value,
                EdgeKind.PRODUCES,
            )

    def _transformation(self, job: PhysicalJob) -> Transformation:
        allocation = self._allocations.job(job)
        return Transformation(
            name=job.name,
            implementation=job.implementation,
            compute=allocation.standard.compute,
            source=job.source,
            allocation=allocation,
        )

    def _node(self, identifier: CanonicalIdentifier) -> _NodeParts:
        return self._nodes.setdefault(
            identifier.value,
            _NodeParts(identifier),
        )

    def _edge(
        self,
        source: str,
        target: str,
        kind: EdgeKind,
        attributes: tuple[tuple[str, str], ...] = (),
    ) -> None:
        edge = LineageEdge(source, target, kind, attributes)
        self._edges[edge.edge_id] = edge


def _dataset_from_activity(
    job: PhysicalJob,
    metadata_index: MetadataIndex,
) -> DatasetMetadata | _ActivityDataset | None:
    activity = job.activity_mapping
    if reference := activity.get("targetDatasetMetadata"):
        return metadata_index.reference(reference)
    dataset = activity.get("dataset")
    if not dataset:
        return None
    return _ActivityDataset(
        dataset_identifier(activity.get("datasetStage", "Unknown"), dataset).value
    )


@dataclass(frozen=True, slots=True)
class _ActivityDataset:
    node_id: str


def _related_jobs(
    direct: set[str],
    dependencies: tuple[tuple[str, str], ...],
    jobs: dict[str, PhysicalJob],
) -> tuple[PhysicalJob, ...]:
    selected = set(direct)
    changed = True
    while changed:
        ancestors = {
            source
            for source, target in dependencies
            if target in selected and source not in selected
        }
        changed = bool(ancestors)
        selected.update(ancestors)
    if len(set(direct)) == 1 and len(jobs) == 1:
        selected.update(jobs)
    return tuple(jobs[key] for key in sorted(selected) if key in jobs)


def _apply_metadata(parts: _NodeParts, metadata: DatasetMetadata) -> None:
    parts.description = metadata.description or parts.description
    parts.versions.add(metadata.version)
    parts.fields.update({field.name: field for field in metadata.fields})
    parts.sources.add(metadata.source)
    parts.attributes["metadataReference"] = metadata.reference


def _output_location(job: PhysicalJob) -> DatasetLocation | None:
    activity = job.activity_mapping
    resource = activity.get("outputResource")
    if not resource:
        return None
    return DatasetLocation(
        resource=resource,
        path_convention=activity.get("outputPathConvention"),
    )


def _context(parts: _NodeParts) -> DerivedContext | None:
    if parts.identifier.kind.value == "job":
        count = len(parts.transformations)
        text = f"Runs {count} source-defined task{'s' if count != 1 else ''}."
    else:
        resources = sorted(location.resource for location in parts.locations)
        text = f"Materialized by {len(parts.transformations)} task(s)" + (
            f" across {', '.join(resources)}." if resources else "."
        )
    return DerivedContext(text=text, generator=CONTEXT_GENERATOR)


def _snowflake_request() -> FunctionExtractionRequest:
    return FunctionExtractionRequest(
        arguments=(
            "de-prod-us-01",
            {"de-prod-us-01"},
            {"pl-datafactory-us-dipipeline-prod-01"},
        ),
        keywords={},
        prefix="snowflake_ingestion",
    )
