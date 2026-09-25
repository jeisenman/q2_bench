"""Lazy MLflow experiment provisioning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from agentsdk.ws.data_engineering.benchmarks.models import Benchmark


class MlflowDependencyError(RuntimeError):
    """Raised when an MLflow operation is requested without MLflow installed."""


class Experiment(Protocol):
    """Minimal experiment value returned by an MLflow client."""

    @property
    def experiment_id(self) -> str:
        """Return the experiment identifier."""


class RunInfo(Protocol):
    """Minimal run information returned by MLflow."""

    @property
    def run_id(self) -> str:
        """Return the run identifier."""


class Run(Protocol):
    """Minimal run returned by MLflow."""

    @property
    def info(self) -> RunInfo:
        """Return run metadata."""


class MlflowClient(Protocol):
    """Minimal client API needed to provision benchmark experiments."""

    def get_experiment_by_name(self, name: str) -> Experiment | None:
        """Find an experiment by name."""

    def create_experiment(
        self,
        name: str,
        artifact_location: str | None = None,
        tags: Mapping[str, object] | None = None,
    ) -> str:
        """Create an experiment and return its identifier."""

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str = "",
        max_results: int = 1000,
    ) -> list[Run]:
        """Search runs in the supplied experiments."""

    def create_run(
        self,
        experiment_id: str,
        tags: Mapping[str, str] | None = None,
        run_name: str | None = None,
    ) -> Run:
        """Create a run."""

    def set_terminated(self, run_id: str, status: str = "FINISHED") -> None:
        """Mark a run complete."""


@dataclass(frozen=True, slots=True)
class MlflowExperimentAdapter:
    """Ensure benchmark experiments exist in an MLflow tracking store."""

    client: MlflowClient

    @classmethod
    def from_tracking_uri(
        cls, tracking_uri: str | None = None
    ) -> MlflowExperimentAdapter:
        """Build an adapter using an installed MLflow client."""
        try:
            mlflow = import_module("mlflow")
            tracking = import_module("mlflow.tracking")
        except ModuleNotFoundError as error:
            message = "MLflow is required; install the optional mlflow dependency."
            raise MlflowDependencyError(message) from error
        if tracking_uri is not None:
            mlflow.set_tracking_uri(tracking_uri)
        client_type = tracking.MlflowClient
        return cls(client=cast("MlflowClient", client_type()))

    def ensure_benchmark(
        self,
        benchmark: Benchmark,
        *,
        artifact_location: str | None = None,
    ) -> str:
        """Ensure the benchmark group experiment exists and return its ID."""
        experiment_name = benchmark.mlflow.experiment_name
        existing = self.client.get_experiment_by_name(experiment_name)
        if existing is not None:
            return existing.experiment_id
        return self.client.create_experiment(
            experiment_name,
            artifact_location=artifact_location,
            tags=benchmark.mlflow.experiment_tags,
        )

    def seed_benchmark(
        self,
        benchmark: Benchmark,
        *,
        artifact_location: str | None = None,
    ) -> str:
        """Create one visible benchmark run when it does not already exist."""
        experiment_id = self.ensure_benchmark(
            benchmark,
            artifact_location=artifact_location,
        )
        escaped_id = benchmark.benchmark_id.replace("'", "\\'")
        existing = self.client.search_runs(
            [experiment_id],
            filter_string=f"tags.`benchmark.id` = '{escaped_id}'",
            max_results=1,
        )
        if existing:
            return existing[0].info.run_id
        tags = {
            **benchmark.mlflow.run_tags,
            "benchmark.display_name": benchmark.display_name,
        }
        run = self.client.create_run(
            experiment_id,
            tags=tags,
            run_name=benchmark.display_name,
        )
        self.client.set_terminated(run.info.run_id)
        return run.info.run_id
