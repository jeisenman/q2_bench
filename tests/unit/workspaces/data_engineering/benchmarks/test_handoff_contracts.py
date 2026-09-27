from pathlib import Path

import pytest

from workspaces.data_engineering.benchmarks.handoff_contracts import (
    HandoffContractError,
    handoff_contract_mapping,
    parse_handoff_contract,
)

PATH = Path("cases.yaml")


def _contract(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "max_parallel": 1,
        "output_authority": "Reporter",
        "agents": [
            {
                "name": "Reporter",
                "parent": "Orchestrator",
                "min_calls": 1,
                "max_calls": 1,
                "required_input_fields": ["findings"],
                "required_output_fields": ["full_report"],
            }
        ],
    }
    value.update(overrides)
    return value


def test_parses_and_serializes_handoff_contract() -> None:
    contract = parse_handoff_contract(_contract(), PATH)

    assert contract is not None
    assert contract.output_authority == "Reporter"
    assert contract.agents[0].required_input_fields == ("findings",)
    assert handoff_contract_mapping(contract)["max_parallel"] == 1
    assert handoff_contract_mapping(None) == {}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("invalid", "must be a mapping"),
        ({"agents": []}, "non-empty list"),
        (_contract(max_parallel=0), "between 1 and 5"),
        (
            _contract(
                agents=[
                    {"name": "Reporter"},
                    {"name": "Reporter"},
                ]
            ),
            "names must be unique",
        ),
        (
            _contract(agents=[{"name": "Reporter", "starts_after": ["Missing"]}]),
            "depends on unknown agents",
        ),
        (
            _contract(agents=[{"name": "Reporter", "starts_after": ["Reporter"]}]),
            "cannot depend on itself",
        ),
        (
            _contract(output_authority="Missing"),
            "output_authority",
        ),
        (
            _contract(agents=["invalid"]),
            "agents must be mappings",
        ),
        (
            _contract(agents=[{"name": ""}]),
            "name must be a non-empty string",
        ),
        (
            _contract(agents=[{"name": "Reporter", "min_calls": 2, "max_calls": 1}]),
            "invalid call bounds",
        ),
        (
            _contract(agents=[{"name": "Reporter", "parent": ""}]),
            "parent",
        ),
        (
            _contract(
                agents=[
                    {"name": "ClusterAgent", "starts_after": ["Reporter"]},
                    {"name": "Reporter", "starts_after": ["ClusterAgent"]},
                ]
            ),
            "contain a cycle",
        ),
        (
            _contract(
                agents=[
                    {
                        "name": "Reporter",
                        "required_input_fields": "invalid",
                    }
                ]
            ),
            "fields must be string lists",
        ),
    ],
)
def test_rejects_invalid_handoff_contracts(
    raw: object,
    message: str,
) -> None:
    with pytest.raises(HandoffContractError, match=message):
        parse_handoff_contract(raw, PATH)


def test_absent_handoff_contract_is_supported() -> None:
    assert parse_handoff_contract(None, PATH) is None
