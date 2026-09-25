"""Agent evaluation port."""

from typing import Protocol

from domain import AgentRequest, AgentResult, BenchmarkIdentity
from domain.models import Attributes


class EvaluationPort(Protocol):
    """Score an agent result against benchmark-owned criteria."""

    async def evaluate(
        self,
        benchmark: BenchmarkIdentity,
        request: AgentRequest,
        result: AgentResult,
    ) -> Attributes:
        """Return immutable evaluation metrics and assessments."""
        ...
