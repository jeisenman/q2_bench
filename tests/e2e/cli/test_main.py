from importlib import import_module
from pathlib import Path

from click.testing import CliRunner

from adapters.mlflow import MlflowExperimentAdapter
from cli.main import cli

main = import_module("cli.main")


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


def test_evaluate_publishes_recorded_case(monkeypatch, tmp_path: Path) -> None:
    recorded = tmp_path / "result.json"
    recorded.write_text("{}", encoding="utf-8")
    loaded = object()
    monkeypatch.setattr(
        main,
        "load_recorded_evaluation",
        lambda cases, case_id, result: (
            loaded
            if case_id == "today-2026-09-25" and result == recorded and cases
            else None
        ),
    )
    monkeypatch.setattr(
        main,
        "publish_recorded_evaluation",
        lambda evaluation, **kwargs: (
            "evaluation-run-1"
            if evaluation is loaded
            and kwargs["experiment_name"] == "production_operations"
            else ""
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "prod-support",
            "--case",
            "today-2026-09-25",
            "--recorded-result",
            str(recorded),
        ],
    )

    assert result.exit_code == 0
    assert result.output == "today-2026-09-25\tevaluation-run-1\n"
