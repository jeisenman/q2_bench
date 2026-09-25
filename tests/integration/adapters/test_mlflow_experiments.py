from dataclasses import dataclass
from typing import Any

from adapters.mlflow import MlflowExperimentAdapter
from workspaces.data_engineering.benchmarks import default_catalog


@dataclass(frozen=True)
class FakeExperiment:
    experiment_id: str


@dataclass(frozen=True)
class FakeRunInfo:
    run_id: str


@dataclass(frozen=True)
class FakeRun:
    info: FakeRunInfo


class FakeMlflowClient:
    def __init__(self) -> None:
        self.experiments: dict[str, FakeExperiment] = {}
        self.created_tags: dict[str, object] = {}
        self.runs: list[FakeRun] = []
        self.run_tags: dict[str, str] = {}
        self.run_name: str | None = None
        self.terminated: list[str] = []

    def get_experiment_by_name(self, name: str) -> FakeExperiment | None:
        return self.experiments.get(name)

    def create_experiment(
        self,
        name: str,
        artifact_location: str | None = None,
        tags: dict[str, Any] | None = None,
    ) -> str:
        del artifact_location
        experiment = FakeExperiment("1")
        self.experiments[name] = experiment
        self.created_tags = dict(tags or {})
        return experiment.experiment_id

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str = "",
        max_results: int = 1000,
    ) -> list[FakeRun]:
        del experiment_ids, filter_string
        return self.runs[:max_results]

    def create_run(
        self,
        experiment_id: str,
        tags: dict[str, str] | None = None,
        run_name: str | None = None,
    ) -> FakeRun:
        del experiment_id
        run = FakeRun(FakeRunInfo("run-1"))
        self.runs.append(run)
        self.run_tags = dict(tags or {})
        self.run_name = run_name
        return run

    def set_terminated(self, run_id: str, status: str = "FINISHED") -> None:
        del status
        self.terminated.append(run_id)


def test_adapter_seeds_prod_support_group_for_mlflow_ui() -> None:
    benchmark = default_catalog().list()[0]
    client = FakeMlflowClient()
    adapter = MlflowExperimentAdapter(client)

    experiment_id = adapter.ensure_benchmark(benchmark)

    assert experiment_id == "1"
    assert benchmark.mlflow.experiment_name in client.experiments
    assert client.created_tags["benchmark.group"] == "production_operations"
    assert adapter.ensure_benchmark(benchmark) == "1"


def test_adapter_seeds_visible_prod_support_run_once() -> None:
    benchmark = default_catalog().list()[0]
    client = FakeMlflowClient()
    adapter = MlflowExperimentAdapter(client)

    run_id = adapter.seed_benchmark(benchmark)

    assert run_id == "run-1"
    assert client.run_name == "prod-support"
    assert client.run_tags["benchmark.display_name"] == "prod-support"
    assert client.terminated == ["run-1"]
    assert adapter.seed_benchmark(benchmark) == "run-1"
