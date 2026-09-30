import json
from importlib import import_module
from pathlib import Path

from click.testing import CliRunner

from adapters.mlflow import MlflowExperimentAdapter
from cli.main import cli

main = import_module("cli.main")
collection_cli = import_module("cli.prod_support_collection")


def test_benchmarks_lists_visible_benchmarks() -> None:
    result = CliRunner().invoke(cli, ["benchmarks"])

    assert result.exit_code == 0
    assert result.output == (
        "anti-leak\tsecurity\n"
        "benchmark-builder\tbenchmark_engineering\n"
        "data-creator\tdata_operations\n"
        "data-finder\tdata_operations\n"
        "data-insight-triage\tproduction_operations\n"
        "etl\tpipeline_engineering\n"
        "kpo-sizer\tplanning\n"
        "prod-bench\tproduction_operations\n"
        "python-upgrade\tpipeline_engineering\n"
        "resource-discovery\tresource_operations\n"
    )


def test_run_matrix_defaults_to_a_grouped_dry_run() -> None:
    candidate_count = 10
    result = CliRunner().invoke(cli, ["run-matrix"])

    assert result.exit_code == 0
    assert (
        result.output.count('"matrix_id": "prod-support-handoffs-09-27-26"')
        == candidate_count
    )
    assert '"profile": "sol-light"' in result.output
    assert '"judge_profile": "sol-high-judge"' in result.output


def test_run_matrix_selects_registered_configuration() -> None:
    result = CliRunner().invoke(
        cli,
        ["run-matrix", "--configuration", "sol-light-luna-high-workers"],
    )

    assert result.exit_code == 0
    assert result.output.count('"profile"') == 1
    assert '"profile": "sol-light-luna-high-workers"' in result.output
    assert '"workers": ["luna-high"]' in result.output


def test_summarize_prod_support_evidence_omits_raw_log_body(tmp_path: Path) -> None:
    dataset = tmp_path / "evidence.json"
    dataset.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "region": "US-01",
                        "dag_id": "dag",
                        "run_id": "run",
                        "task_id": "task",
                        "start_at": "2026-09-25T05:00:00+00:00",
                        "end_at": "2026-09-25T06:00:00+00:00",
                        "try_number": 1,
                        "log": ("progress\\n" * 10_000) + "OOMKilled",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        [
            "summarize-prod-support-evidence",
            "--dataset",
            str(dataset),
            "--start",
            "2026-09-25T05:00:00Z",
            "--end",
            "2026-09-26T05:00:00Z",
        ],
    )

    record = json.loads(result.output)
    assert result.exit_code == 0
    assert record["log_retrieval"] == "exact_replay_task_attempt"
    assert record["log_status"] == "terminal"
    assert record["evidence"] == ["OOMKilled"]
    assert "progress" not in result.output


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
    assert result.output == (
        "anti-leak\trun-1\n"
        "benchmark-builder\trun-1\n"
        "data-creator\trun-1\n"
        "data-finder\trun-1\n"
        "data-insight-triage\trun-1\n"
        "etl\trun-1\n"
        "kpo-sizer\trun-1\n"
        "prod-bench\trun-1\n"
        "python-upgrade\trun-1\n"
        "resource-discovery\trun-1\n"
    )
    assert seeded == [
        "anti-leak",
        "benchmark-builder",
        "data-creator",
        "data-finder",
        "data-insight-triage",
        "etl",
        "kpo-sizer",
        "prod-bench",
        "python-upgrade",
        "resource-discovery",
    ]


def test_configure_codex_tracing_reports_written_paths(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"

    result = CliRunner().invoke(
        cli,
        [
            "configure-codex-tracing",
            "--tracking-uri",
            "http://mlflow:5000",
            "--experiment-id",
            "42",
            "--codex-home",
            str(codex_home),
            "--project-root",
            str(project_root),
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        f"codex-config\t{codex_home / 'config.toml'}\n"
        f"tracing-config\t{project_root / '.codex/mlflow-tracing.json'}\n"
    )


def test_debug_prod_support_reports_local_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class Outcome:
        report = "debug report"
        failures = ()

    class Artifacts:
        outcome = Outcome()
        dataset = tmp_path / "airflow_failures.json"
        benchmark_root = tmp_path / "benchmark"

    def fake_source() -> object:
        return object()

    monkeypatch.setattr(
        collection_cli.AirflowApiSource,
        "from_configuration",
        staticmethod(fake_source),
    )
    monkeypatch.setattr(
        collection_cli.ClusterHealthScriptSource,
        "from_repository",
        staticmethod(fake_source),
    )
    monkeypatch.setattr(
        collection_cli.ResourceDiscoveryApiSource,
        "from_environment",
        staticmethod(fake_source),
    )

    async def fake_run(
        sources,
        operational_date,
        output_root,
        *,
        regions,
    ):
        assert sources.airflow is not None
        assert sources.cluster_health is not None
        assert sources.resource_discovery is not None
        assert operational_date.isoformat() == "2026-09-25"
        assert output_root == Path("var/benchmark_data/production_support")
        assert [region.value for region in regions] == ["US-01", "CA-02"]
        return Artifacts()

    monkeypatch.setattr(collection_cli, "run_debug_day", fake_run)

    result = CliRunner().invoke(
        cli,
        [
            "debug-prod-support",
            "--date",
            "2026-09-25",
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        f"captured\t0 failures\treview required before promotion\n"
        f"dataset\t{Artifacts.dataset}\n"
        f"benchmark\t{Artifacts.benchmark_root}\n"
    )


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
