import asyncio

from domain import AgentRequest
from workspaces.data_engineering.agents.anti_leak import (
    AntiLeakAgent,
    ContainerEvidence,
    MountedPath,
    scan_v1,
)


class FixtureSource:
    def load(self) -> ContainerEvidence:
        return ContainerEvidence(
            user="root",
            read_only_root=False,
            environment=("TOKEN=CANARY",),
            mounts=(
                MountedPath(
                    source="/var/run/docker.sock",
                    destination="/var/run/docker.sock",
                    read_only=False,
                ),
            ),
            capabilities=("ALL",),
            visible_files=("/workspace/.env", "/benchmark/hidden/answers.yaml"),
        )


def test_v1_is_intentionally_incomplete() -> None:
    findings = scan_v1(FixtureSource().load())

    assert tuple(item.finding_id for item in findings) == (
        "root-user",
        "visible-dotenv",
    )


def test_agent_reports_baseline_and_marks_it_incomplete() -> None:
    result = asyncio.run(
        AntiLeakAgent(FixtureSource()).run(
            AgentRequest(prompt="Audit it", correlation_id="anti-leak-1")
        )
    )

    assert "[high] root-user" in result.output
    assert "[high] visible-dotenv" in result.output
    assert "CANARY" not in result.output
    assert ("known_incomplete", True) in result.attributes
    assert result.tool_calls == ("load_container_evidence",)
