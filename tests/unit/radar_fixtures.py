from __future__ import annotations

import subprocess
from pathlib import Path

from workspaces.data_engineering.workflows.lineage import RadarRepositories


def create_radar_repositories(
    tmp_path: Path,
    di_repository: Path,
) -> RadarRepositories:
    repositories = RadarRepositories(
        di_pipelines=di_repository,
        radar_notebooks=tmp_path / "radar-notebooks",
        radar_libraries=tmp_path / "radar-libraries",
        radar_adf=tmp_path / "radar-adf-pipeline",
        data_ingress=tmp_path / "pl-dataingress",
        calculation_engine=tmp_path / "pl-calculation-engine",
    )
    _radar_libraries(repositories.radar_libraries)
    _radar_notebooks(repositories.radar_notebooks)
    _radar_adf(repositories.radar_adf)
    _data_ingress(repositories.data_ingress)
    _calculation_engine(repositories.calculation_engine)
    for name, repository in repositories.as_mapping().items():
        if name == "di-pipelines":
            continue
        branch = "develop" if name == "pl-calculation-engine" else "master"
        _initialize(repository, name, branch)
    return repositories


def _radar_libraries(repository: Path) -> None:
    _write(
        repository / "radar_libraries/fileio/loader.py",
        """
def load_extracted_client_file(env, run_path, filename):
    return filename

def loadAssumptionSets(env, run_path):
    filename = os.path.join(run_path, "ApplicationInput", "AssumptionSets.csv")
    return filename

def loadMappedRelationships(env, run_path):
    filename = os.path.join(run_path, "MappingResults", "MappedRelationships.csv")
    return filename
""",
    )
    _write(
        repository / "radar_libraries/fileio/outputter.py",
        """
def output_extracted_client_file(env, run_path, filename, dataframe, columns):
    return filename

def outputMappedRelationships(env, run_path, dataframe):
    filename = os.path.join(run_path, "MappingResults", "MappedRelationships.csv")
    return filename

def outputTransformedRelationships(env, run_path, dataframe):
    filename = os.path.join(
        run_path, "TransformResults", "TransformedRelationships.csv"
    )
    return filename
""",
    )


def _radar_notebooks(repository: Path) -> None:
    root = repository / "notebooks/Shared"
    _write(
        root / "Clients/Test/Extract_Relationships_Test.py",
        """
OUTPUT_FILE_NAME = "RawInputs_Relationships"
outputter.output_extracted_client_file(
    spark_env, ADLS_RUN_PATH, OUTPUT_FILE_NAME, valid, columns
)
""",
    )
    _write(
        root / "Clients/Test/Map_Relationships_Test.py",
        """
raw = loader.load_extracted_client_file(
    spark_env, ADLS_RUN_PATH, "RawInputs_Relationships"
)
assumptions = loader.loadAssumptionSets(spark_env, ADLS_RUN_PATH)
outputter.outputMappedRelationships(spark_env, ADLS_RUN_PATH, raw)
""",
    )
    _write(
        root / "Universal/Transform_Relationships.py",
        """
mapped = loader.loadMappedRelationships(spark_env, ADLS_RUN_PATH)
outputter.outputTransformedRelationships(spark_env, ADLS_RUN_PATH, mapped)
""",
    )


def _radar_adf(repository: Path) -> None:
    _write(
        repository / "pipeline/radar-mapping-batch.json",
        """
{
  "activities": [
    {"name": "File Extraction"},
    {"name": "Relationship Mapping"}
  ]
}
""",
    )
    _write(
        repository / "pipeline/transform-calculation-batch.json",
        """
{
  "activities": [
    {"name": "Relationship Transform"},
    {"name": "Relationship Family Calculation"},
    {"name": "Output Final CSVs"},
    {"name": "Output Data Engineering CSVs"}
  ]
}
""",
    )


def _data_ingress(repository: Path) -> None:
    _write(
        repository / "PrecisionLender.DataIngress.Persistence/Client/Schema.xml",
        """
<Schema><OutputFiles>
  <RunFile Name="A" Folder="ApplicationInput" FileName="AssumptionSets" />
  <RunFile Name="M" Folder="MappingResults" FileName="MappedRelationships" />
  <RunFile Name="T" Folder="TransformResults" FileName="TransformedRelationships" />
  <RunFile Name="C" Folder="EngineResults" FileName="CalculatedRelationships" />
  <RunFile Name="D" Folder="DataEngineering" FileName="" />
  <RunFile Name="O" Folder="DatabaseOutput" FileName="dbStagingRelationshipNew" />
</OutputFiles></Schema>
""",
    )
    _write(
        repository / "PrecisionLender.DataIngress.Calculations/EngineMapping/"
        "RelationshipEngineMapping.cs",
        "internal static object MapRelationship(object relationship) => relationship;",
    )
    _write(
        repository / "PrecisionLender.DataIngress.Calculations/RadarDtos/"
        "RadarRelationship.cs",
        "public void BuildCalculationObjects(object settings) { }",
    )
    _write(
        repository / "PrecisionLender.DataIngress.Calculations/Calculators/"
        "RelationshipCalculator.cs",
        "public object CalculateRelationshipFamily(object family) => family;",
    )
    _write(
        repository
        / "PrecisionLender.DataIngress.BatchProcessing/BatchOperationRunner.cs",
        """
await DataEngineeringOutputBatchOperation.RunAsync();
await DatabaseOutputBatchOperation.RunAsync();
""",
    )


def _calculation_engine(repository: Path) -> None:
    _write(
        repository / "PrecisionLender.Common.Engine.EngineService/Interfaces/"
        "IRARelationshipEngineService.cs",
        """
public interface IRARelationshipEngineService
{
    IRelationshipResult CalculateRelationship(object relationship);
}
""",
    )
    _write(
        repository / "PrecisionLender.Common.Engine.EngineService/"
        "RARelationshipEngineService.cs",
        """
public class RARelationshipEngineService
{
    public IRelationshipResult CalculateRelationship(object relationship) => null;
}
""",
    )


def _initialize(repository: Path, name: str, branch: str) -> None:
    _git(repository, "init", "-b", branch)
    _git(repository, "config", "user.email", "lineage@example.com")
    _git(repository, "config", "user.name", "Lineage Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "fixture")
    _git(
        repository,
        "remote",
        "add",
        "origin",
        f"git@github.com:precisionlender/{name}.git",
    )


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
