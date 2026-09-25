from pathlib import Path

from click.testing import CliRunner

from agentsdk.adapters.mlflow import MlflowExperimentAdapter
from agentsdk.cli.main import cli


def test_benchmarks_lists_prod_support() -> None:
    result = CliRunner().invoke(cli, ["benchmarks"])

    assert result.exit_code == 0
    assert result.output == "prod-support\tproduction_operations\n"


def test_init_seeds_benchmark(monkeypatch, tmp_path: Path) -> None:
    seeded: list[str] = []

    class FakeAdapter:
        def seed_benchmark(self, benchmark, *, artifact_location=None) -> str:
            assert artifact_location is not None
            seeded.append(benchmark.display_name)
            return "run-1"

    monkeypatch.setattr(
        MlflowExperimentAdapter,
        "from_tracking_uri",
        staticmethod(lambda _tracking_uri: FakeAdapter()),
    )

    result = CliRunner().invoke(
        cli,
        ["init", "--artifact-root", str(tmp_path / "artifacts")],
    )

    assert result.exit_code == 0
    assert result.output == "prod-support\trun-1\n"
    assert seeded == ["prod-support"]
