from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.lineage import sync_lineage


def test_lineage_cli_builds_review_artifact(
    di_repository: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "lineage/graph.json"
    result = CliRunner().invoke(
        sync_lineage,
        (
            "--repository",
            str(di_repository),
            "--source-ref",
            "master",
            "--dry-run",
            "--output",
            str(output),
        ),
    )

    assert result.exit_code == 0, result.output
    assert "precisionlender/di-pipelines" in result.output
    assert "not-persisted" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["manifest"]["sourceRef"] == "master"
    assert payload["nodes"]
    assert payload["edges"]


def test_lineage_cli_validates_repository_and_storage_configuration(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    missing = runner.invoke(
        sync_lineage,
        ("--repository", str(tmp_path / "missing"), "--dry-run"),
    )
    no_dsn_repository = tmp_path / "repository"
    no_dsn_repository.mkdir()
    no_dsn = runner.invoke(
        sync_lineage,
        ("--repository", str(no_dsn_repository)),
    )

    assert missing.exit_code != 0
    assert "does not exist" in missing.output
    assert no_dsn.exit_code != 0
    assert "LINEAGE_POSTGRES_DSN" in no_dsn.output
