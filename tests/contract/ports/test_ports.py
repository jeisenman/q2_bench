from pathlib import Path

from domain import AgentRequest, AgentResult, BenchmarkIdentity
from domain.models import Attributes
from ports import (
    ArtifactPort,
    DatasetProvider,
    EvaluationPort,
    SecretProvider,
    TrackingPort,
)


class FakeProvider:
    async def fetch_records(
        self,
        dataset: str,
        *,
        filters: Attributes = (),
        limit: int = 100,
    ) -> tuple[Attributes, ...]:
        del filters
        return ((("dataset", dataset), ("limit", limit)),)


class FakeTracking:
    async def start_run(
        self, benchmark: BenchmarkIdentity, request: AgentRequest
    ) -> str:
        return f"{benchmark.qualified_name}:{request.correlation_id}"

    async def log_result(self, run_id: str, result: AgentResult) -> None:
        del run_id, result

    async def annotate_failure(
        self,
        run_id: str,
        category: str,
        details: str,
        *,
        attributes: Attributes = (),
    ) -> None:
        del run_id, category, details, attributes


class FakeEvaluation:
    async def evaluate(
        self,
        benchmark: BenchmarkIdentity,
        request: AgentRequest,
        result: AgentResult,
    ) -> Attributes:
        del benchmark, request, result
        return (("score", 1.0),)


class FakeArtifacts:
    async def put(self, run_id: str, name: str, source: Path) -> str:
        del source
        return f"artifact://{run_id}/{name}"

    async def get(self, uri: str, destination: Path) -> Path:
        del uri
        return destination


class FakeSecrets:
    async def get_secret(self, name: str) -> str:
        return f"secret:{name}"


def test_fakes_satisfy_port_contracts() -> None:
    datasets: DatasetProvider = FakeProvider()
    tracking: TrackingPort = FakeTracking()
    evaluation: EvaluationPort = FakeEvaluation()
    artifacts: ArtifactPort = FakeArtifacts()
    secrets: SecretProvider = FakeSecrets()

    assert all((datasets, tracking, evaluation, artifacts, secrets))
