from importlib import import_module
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.main import cli

collection_cli = import_module("cli.prod_support_collection")


def test_capture_prod_support_reports_complete_bundle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class Bundle:
        airflow = tmp_path / "airflow_failures.json"
        cluster_health = tmp_path / "cluster_health.json"
        resource_discovery = tmp_path / "resource_discovery.json"
        compact_evidence = tmp_path / "compact_evidence.json"
        reporting_input = tmp_path / "reporting_input.json"
        manifest = tmp_path / "collection_manifest.json"

    sources = object()
    monkeypatch.setattr(collection_cli, "_production_sources", lambda: sources)

    async def fake_collect(
        actual_sources,
        operational_date,
        destination,
        *,
        regions,
    ):
        assert actual_sources is sources
        assert operational_date.isoformat() == "2026-09-25"
        assert destination == tmp_path / "2026-09-25"
        assert [region.value for region in regions] == ["CA-02"]
        return Bundle()

    monkeypatch.setattr(collection_cli, "collect_prod_support_data", fake_collect)

    result = CliRunner().invoke(
        cli,
        [
            "capture-prod-support",
            "--date",
            "2026-09-25",
            "--output-root",
            str(tmp_path),
            "--scope",
            "ca",
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        f"airflow\t{Bundle.airflow}\n"
        f"cluster_health\t{Bundle.cluster_health}\n"
        f"resource_discovery\t{Bundle.resource_discovery}\n"
        f"compact_evidence\t{Bundle.compact_evidence}\n"
        f"reporting_input\t{Bundle.reporting_input}\n"
        f"manifest\t{Bundle.manifest}\n"
    )


def test_prod_support_capture_scope_validation() -> None:
    assert [region.value for region in collection_cli.capture_regions("US")] == [
        "US-01"
    ]
    assert [region.value for region in collection_cli.capture_regions("both")] == [
        "US-01",
        "CA-02",
    ]
    with pytest.raises(ValueError, match="scope"):
        collection_cli.capture_regions("invalid")
