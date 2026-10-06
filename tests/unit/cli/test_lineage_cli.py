from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.lineage import sync_lineage
from workspaces.data_engineering.workflows.lineage import RadarRepositories

SOURCE_REPOSITORY_COUNT = 6


def test_lineage_cli_builds_review_artifact(
    radar_repositories: RadarRepositories,
    tmp_path: Path,
) -> None:
    output = tmp_path / "lineage/graph.json"
    result = CliRunner().invoke(
        sync_lineage,
        (
            *_repository_args(radar_repositories),
            "--source-ref",
            "static-analysis",
            "--dry-run",
            "--output",
            str(output),
        ),
    )

    assert result.exit_code == 0, result.output
    assert "precisionlender/radar-lineage" in result.output
    assert "not-persisted" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["manifest"]["sourceRef"] == "static-analysis"
    assert len(payload["manifest"]["sourceRepositories"]) == SOURCE_REPOSITORY_COUNT
    assert payload["nodes"]
    assert payload["edges"]


def test_lineage_cli_validates_repository_and_storage_configuration(
    radar_repositories: RadarRepositories,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    missing = runner.invoke(
        sync_lineage,
        (
            *_repository_args(radar_repositories),
            "--repository",
            str(tmp_path / "missing"),
            "--dry-run",
        ),
    )
    no_dsn = runner.invoke(
        sync_lineage,
        _repository_args(radar_repositories),
    )

    assert missing.exit_code != 0
    assert "does not exist" in missing.output
    assert no_dsn.exit_code != 0
    assert "LINEAGE_POSTGRES_DSN" in no_dsn.output


def _repository_args(repositories: RadarRepositories) -> tuple[str, ...]:
    return (
        "--repository",
        str(repositories.di_pipelines),
        "--radar-notebooks-repository",
        str(repositories.radar_notebooks),
        "--radar-libraries-repository",
        str(repositories.radar_libraries),
        "--radar-adf-repository",
        str(repositories.radar_adf),
        "--data-ingress-repository",
        str(repositories.data_ingress),
        "--engine-repository",
        str(repositories.calculation_engine),
    )
