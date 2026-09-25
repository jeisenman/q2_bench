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


def test_run_matrix_defaults_to_a_grouped_dry_run() -> None:
    candidate_count = 6
    result = CliRunner().invoke(cli, ["run-matrix"])

    assert result.exit_code == 0
    assert (
        result.output.count('"matrix_id": "prod-support-09-25-26"') == candidate_count
    )
    assert '"profile": "sol-light"' in result.output
    assert '"judge_profile": "sol-xhigh"' in result.output


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
            if case_id == "prod-support-us-ca-2026-09-25"
            and result == recorded
            and cases
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
            "prod-support-us-ca-2026-09-25",
            "--recorded-result",
            str(recorded),
        ],
    )

    assert result.exit_code == 0
    assert result.output == "prod-support-us-ca-2026-09-25\tevaluation-run-1\n"


def test_replay_evaluate_runs_and_publishes_case(monkeypatch, tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.json"
    dataset.write_text("{}", encoding="utf-8")
    output = tmp_path / "result.json"
    case = object()
    outcome = object()
    evaluation = object()
    monkeypatch.setattr(
        main,
        "load_replay_case",
        lambda _cases, _case_id: case,
    )
    monkeypatch.setattr(
        main,
        "run_replay_case",
        lambda loaded, path: outcome if loaded is case and path == dataset else None,
    )
    monkeypatch.setattr(
        main,
        "write_recorded_outcome",
        lambda loaded, path: path if loaded is outcome and path == output else None,
    )
    monkeypatch.setattr(
        main,
        "load_recorded_evaluation",
        lambda cases, case_id, path: (
            evaluation
            if case_id == "prod-support-us-ca-2026-09-25" and path == output and cases
            else None
        ),
    )
    monkeypatch.setattr(
        main,
        "publish_recorded_evaluation",
        lambda loaded, **kwargs: (
            "evaluation-run-2"
            if loaded is evaluation and kwargs["tracking_uri"] == "http://mlflow:5000"
            else ""
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "replay-evaluate",
            "prod-support",
            "--case",
            "prod-support-us-ca-2026-09-25",
            "--dataset",
            str(dataset),
            "--output",
            str(output),
            "--tracking-uri",
            "http://mlflow:5000",
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        f"prod-support-us-ca-2026-09-25\tevaluation-run-2\t{output}\n"
    )
