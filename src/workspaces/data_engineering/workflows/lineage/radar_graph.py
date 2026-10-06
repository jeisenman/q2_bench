"""Compose RADAR repositories into one structural lineage graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.enrichments import (
    NodeEnrichment,
    SourceLocation,
)
from workspaces.data_engineering.workflows.lineage.graph_models import (
    LineageGraph,
    RepositoryManifest,
)
from workspaces.data_engineering.workflows.lineage.identifiers import (
    airflow_job_identifier,
    radar_job_identifier,
)
from workspaces.data_engineering.workflows.lineage.main_graph import IntendedDag
from workspaces.data_engineering.workflows.lineage.models import (
    DerivedContext,
    EdgeKind,
    LineageNode,
    Transformation,
)
from workspaces.data_engineering.workflows.lineage.radar_accumulator import (
    RadarGraphAccumulator,
)
from workspaces.data_engineering.workflows.lineage.radar_engine_sources import (
    adf_activity_sources,
    engine_calculations,
    text_source,
)
from workspaces.data_engineering.workflows.lineage.radar_graph_support import (
    prefix_di_sources,
    stage_description,
)
from workspaces.data_engineering.workflows.lineage.radar_repositories import (
    RadarRepositories,
)
from workspaces.data_engineering.workflows.lineage.radar_sources import (
    NotebookEvidence,
    notebook_evidence,
    run_file_contracts,
)

CONTEXT_GENERATOR = "q2-radar-lineage-static-context-v1"
DTO_PATH = "EngineDTO/RelationshipFamilies"
CLIENT_UPLOAD_PATH = "ClientUploadedFiles"
_STAGE_ACTIVITIES = {
    "extract": ("File Extraction",),
    "mapping": (
        "Relationship Mapping",
        "Commercial Loan Mapping",
        "Deposit Mapping",
        "Other Mapping",
        "Treasury Mapping",
    ),
    "transform": (
        "Relationship Transform",
        "Commercial Loan Transform",
        "Deposit Transform",
        "Other Transform",
        "Treasury Transform",
        "Build Hierarchy",
    ),
}


@dataclass(frozen=True, slots=True)
class _OutputJob:
    name: str
    description: str
    folder: str
    activities: tuple[str, ...]
    source_needle: str


class RadarGraphBuilder(RadarGraphAccumulator):
    """Add pre-DI RADAR stages and connect their files to DI Pipelines."""

    def __init__(self, repositories: RadarRepositories) -> None:
        """Initialize the aggregate builder from explicit checkouts."""
        super().__init__()
        self._repositories = repositories

    def build(
        self,
        manifest: RepositoryManifest,
        di_graph: LineageGraph,
        intended: IntendedDag,
    ) -> LineageGraph:
        """Return the deterministic aggregate graph."""
        prefixed = prefix_di_sources(di_graph)
        self._nodes = {node.node_id: node for node in prefixed.nodes}
        self._edges = {edge.edge_id: edge for edge in prefixed.edges}
        self._contracts = {
            item.path: item
            for item in run_file_contracts(self._repositories.data_ingress)
        }
        for contract in self._contracts.values():
            self._add_file(contract.path, (contract.source,))

        notebooks = notebook_evidence(
            self._repositories.radar_notebooks,
            self._repositories.radar_libraries,
        )
        stage_jobs = {
            stage: self._add_notebook_stage(stage, notebooks)
            for stage in ("extract", "mapping", "transform")
        }
        self._depends(stage_jobs["extract"], stage_jobs["mapping"])
        self._depends(stage_jobs["mapping"], stage_jobs["transform"])
        self._add_calculation_stages(stage_jobs["transform"])
        self._link_di_inputs(intended)
        return LineageGraph(
            manifest,
            tuple(sorted(self._nodes.values(), key=lambda item: item.node_id)),
            tuple(sorted(self._edges.values(), key=lambda item: item.edge_id)),
        )

    def _add_notebook_stage(
        self,
        stage: str,
        notebooks: tuple[NotebookEvidence, ...],
    ) -> str:
        selected = tuple(item for item in notebooks if item.stage == stage)
        adf_sources = adf_activity_sources(
            self._repositories.radar_adf,
            _STAGE_ACTIVITIES[stage],
        )
        transformations = [
            Transformation(
                name=item.implementation,
                implementation="Databricks notebook",
                compute="databricks",
                source=item.source,
            )
            for item in selected
        ]
        transformations.extend(
            Transformation(
                name=f"{stage} ADF orchestration",
                implementation="Azure Data Factory activity",
                compute="adf",
                source=source,
            )
            for source in adf_sources
        )
        identifier = radar_job_identifier("radar-notebooks", stage)
        job = LineageNode(
            identifier=identifier,
            description=stage_description(stage),
            transformations=tuple(
                sorted(
                    transformations,
                    key=lambda item: (item.name, item.source.path, item.source.line),
                )
            ),
            sources=tuple(
                sorted(
                    {
                        *adf_sources,
                        *(item.source for item in selected),
                    },
                    key=lambda item: (item.path, item.line),
                )
            ),
            owners=("precisionlender",),
            context=DerivedContext(
                f"Static maximum-client union of {len(selected)} {stage} notebooks.",
                CONTEXT_GENERATOR,
            ),
            attributes=(
                ("component", "radar-notebooks"),
                ("scope", "all-client-static-union"),
                ("stage", stage),
            ),
        )
        self._nodes[job.node_id] = job
        if stage == "extract":
            uploaded = self._add_file(
                CLIENT_UPLOAD_PATH,
                adf_sources,
                "Client-provided files at the start of a RADAR run.",
            )
            self._edge(uploaded, job.node_id, EdgeKind.CONSUMES)
        for notebook in selected:
            for reference in notebook.inputs:
                dataset = self._add_file(
                    reference.path,
                    (reference.library_source, reference.call_source),
                )
                self._edge(dataset, job.node_id, EdgeKind.CONSUMES)
            for reference in notebook.outputs:
                dataset = self._add_file(
                    reference.path,
                    (reference.library_source, reference.call_source),
                )
                self._edge(job.node_id, dataset, EdgeKind.PRODUCES)
        return job.node_id

    def _add_calculation_stages(self, transform_job: str) -> None:
        dto_sources = (
            text_source(
                self._repositories.data_ingress,
                "pl-dataingress",
                Path(
                    "PrecisionLender.DataIngress.Calculations/"
                    "EngineMapping/RelationshipEngineMapping.cs"
                ),
                "MapRelationship(",
            ),
            text_source(
                self._repositories.data_ingress,
                "pl-dataingress",
                Path(
                    "PrecisionLender.DataIngress.Calculations/"
                    "RadarDtos/RadarRelationship.cs"
                ),
                "BuildCalculationObjects(",
            ),
        )
        dto_job = self._simple_job(
            "pl-dataingress",
            "engine-dto-mapping",
            "Maps TransformResults relationship families into computable engine DTOs.",
            dto_sources,
        )
        for path in self._paths("TransformResults"):
            self._edge(self._add_file(path), dto_job, EdgeKind.CONSUMES)
        dto_dataset = self._add_file(
            DTO_PATH,
            dto_sources,
            "In-memory computable relationship and account DTO shapes.",
            resource="DataIngress.EngineDTO",
        )
        self._edge(dto_job, dto_dataset, EdgeKind.PRODUCES)
        self._depends(transform_job, dto_job)

        calculation_source = text_source(
            self._repositories.data_ingress,
            "pl-dataingress",
            Path(
                "PrecisionLender.DataIngress.Calculations/"
                "Calculators/RelationshipCalculator.cs"
            ),
            "CalculateRelationshipFamily(",
        )
        adf_calculation = adf_activity_sources(
            self._repositories.radar_adf,
            ("Relationship Family Calculation",),
        )
        calculation_job = self._simple_job(
            "pl-calculation-engine",
            "relationship-family-calculation",
            "Runs relationship and account calculations from computable DTOs.",
            (calculation_source, *adf_calculation),
            enrichments=tuple(
                NodeEnrichment(
                    category="engine-calculation",
                    name=f"{item.service}.{item.method}",
                    description=(
                        "Public RADAR calculation contract exposed by the engine."
                    ),
                    sources=item.sources,
                    attributes=(("representation", "enrichment-only"),),
                )
                for item in engine_calculations(self._repositories.calculation_engine)
            ),
        )
        self._edge(dto_dataset, calculation_job, EdgeKind.CONSUMES)
        self._depends(dto_job, calculation_job)
        for path in self._paths("EngineResults"):
            self._edge(calculation_job, self._add_file(path), EdgeKind.PRODUCES)

        self._add_output_job(
            calculation_job,
            _OutputJob(
                "database-output",
                "Converts EngineResults into downstream DatabaseOutput files.",
                "DatabaseOutput",
                ("Output Final CSVs",),
                "await DatabaseOutputBatchOperation.RunAsync(",
            ),
        )
        self._add_output_job(
            calculation_job,
            _OutputJob(
                "data-engineering-output",
                "Converts EngineResults into DataEngineering metadata files.",
                "DataEngineering",
                ("Output Data Engineering CSVs",),
                "await DataEngineeringOutputBatchOperation.RunAsync(",
            ),
        )

    def _add_output_job(
        self,
        calculation_job: str,
        output: _OutputJob,
    ) -> None:
        sources = (
            text_source(
                self._repositories.data_ingress,
                "pl-dataingress",
                Path(
                    "PrecisionLender.DataIngress.BatchProcessing/"
                    "BatchOperationRunner.cs"
                ),
                output.source_needle,
            ),
            *adf_activity_sources(
                self._repositories.radar_adf,
                output.activities,
            ),
        )
        job = self._simple_job(
            "pl-dataingress",
            output.name,
            output.description,
            sources,
        )
        self._depends(calculation_job, job)
        for path in self._paths("EngineResults"):
            self._edge(self._add_file(path), job, EdgeKind.CONSUMES)
        for path in self._paths(output.folder):
            self._edge(job, self._add_file(path), EdgeKind.PRODUCES)

    def _simple_job(
        self,
        component: str,
        name: str,
        description: str,
        sources: tuple[SourceLocation, ...],
        *,
        enrichments: tuple[NodeEnrichment, ...] = (),
    ) -> str:
        identifier = radar_job_identifier(component, name)
        self._nodes[identifier.value] = LineageNode(
            identifier=identifier,
            description=description,
            transformations=tuple(
                Transformation(
                    name=name,
                    implementation=component,
                    compute="batch",
                    source=source,
                )
                for source in sources
            ),
            sources=sources,
            owners=("precisionlender",),
            context=DerivedContext(description, CONTEXT_GENERATOR),
            attributes=(("component", component),),
            enrichments=enrichments,
        )
        return identifier.value

    def _link_di_inputs(self, intended: IntendedDag) -> None:
        for invocation in intended.invocations:
            target = airflow_job_identifier(intended.dag_id, invocation.key).value
            for job in invocation.physical.jobs:
                path = job.activity_mapping.get("raFile")
                if not path:
                    continue
                source = SourceLocation(
                    f"di-pipelines/{job.source.path}",
                    job.source.line,
                )
                dataset = self._add_file(path, (source,))
                self._edge(
                    dataset,
                    target,
                    EdgeKind.CONSUMES,
                    (("evidence", "di_pipelines_raFile"),),
                )
