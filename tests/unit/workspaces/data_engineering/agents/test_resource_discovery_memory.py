import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from adapters.local import InMemoryAgentMemoryStore
from adapters.resource_discovery import (
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
)
from agent_memory import AgentMemory, MemoryScope, MemoryScopeType
from domain import AgentRequest
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
    ResourceIdentifier,
)

CLIENT_UUID = "11111111-1111-1111-1111-111111111111"


class RecordingRemoteSource:
    def __init__(self) -> None:
        self.identifiers: list[ResourceIdentifier] = []

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[Mapping[str, object], ...]:
        self.identifiers.append(identifier)
        return ()


def agent(tmp_path: Path) -> tuple[ResourceDiscoveryAgent, RecordingRemoteSource]:
    lookup = tmp_path / "clients.json"
    lookup.write_text(
        json.dumps(
            {
                CLIENT_UUID: {
                    "name": "City National Bank",
                    "source": "resource-discovery-api",
                    "api_status": "unique-match",
                }
            }
        ),
        encoding="utf-8",
    )
    remote = RecordingRemoteSource()
    source = IndexedResourceDiscoverySource(remote, JsonClientLookupSource(lookup))
    memory = AgentMemory(
        InMemoryAgentMemoryStore(),
        agent_id="resource-discovery",
        scope=MemoryScope(
            tenant_id="q2",
            scope_type=MemoryScopeType.TEAM,
            scope_id="data-engineering",
        ),
    )
    return ResourceDiscoveryAgent(source, memory=memory), remote


def lookup_request(prompt: str) -> AgentRequest:
    return AgentRequest(prompt=prompt, correlation_id="lookup")


def feedback_request(memory_id: str, confirmation_number: int) -> AgentRequest:
    return AgentRequest(
        prompt="Confirm the proposed alias.",
        correlation_id=f"confirm-{confirmation_number}-{memory_id}",
        attributes=(
            ("memory_id", memory_id),
            ("memory_outcome", "confirmed"),
        ),
    )


def test_exact_json_name_short_circuits_remote_lookup(tmp_path: Path) -> None:
    resource_agent, remote = agent(tmp_path)

    result = asyncio.run(resource_agent.run(lookup_request("find City National Bank?")))

    assert "Finding: unique match" in result.output
    assert CLIENT_UUID in result.output
    assert remote.identifiers == []


def test_alias_is_confirmed_then_resolved_without_remote_lookup(
    tmp_path: Path,
) -> None:
    resource_agent, remote = agent(tmp_path)

    proposed = asyncio.run(resource_agent.run(lookup_request("find the CNB?")))
    attributes = dict(proposed.attributes)
    memory_id = str(attributes["memory_id"])

    assert proposed.output.startswith("By CNB, do you mean City National Bank")
    assert attributes["status"] == "confirmation_required"
    for confirmation_number in range(3):
        confirmation = asyncio.run(
            resource_agent.run(feedback_request(memory_id, confirmation_number))
        )
    resolved = asyncio.run(resource_agent.run(lookup_request("find CNB?")))

    assert "Confirmed alias memory" in confirmation.output
    assert "Finding: unique match" in resolved.output
    assert CLIENT_UUID in resolved.output
    assert ("memory_resolution", "confirmed") in resolved.attributes
    assert remote.identifiers == []
