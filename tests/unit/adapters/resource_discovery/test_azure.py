import asyncio
import json
import subprocess

import pytest

from adapters.resource_discovery import AzureResourceError, AzureResourceSource

PRODUCTION_SUBSCRIPTION = "71aa0ec0-8411-43a2-9908-ddd2add764eb"
PREPROD_SUBSCRIPTION = "cde221ff-e7f4-4d39-be20-6f9d532cab60"
DATA_ENGINEERING_SUBSCRIPTION = "b7b3f313-bcc8-4754-aa71-a8c9a910841c"
EXPECTED_RESOURCE_COUNT = 2
EXPECTED_ACCOUNT_COMMAND_COUNT = 2


class FakeRunner:
    def __init__(self, results):
        self.results = iter(results)
        self.commands = []

    def run(self, arguments):
        self.commands.append(tuple(arguments))
        return next(self.results)


def _result(returncode: int = 0, stdout: str = ""):
    return subprocess.CompletedProcess(("az",), returncode, stdout, "")


@pytest.mark.parametrize(
    ("target", "subscription_id"),
    [
        ("ra_preprod", PREPROD_SUBSCRIPTION),
        ("data_engineering", DATA_ENGINEERING_SUBSCRIPTION),
        ("production", PRODUCTION_SUBSCRIPTION),
    ],
)
def test_azure_source_selects_target_subscription(
    target: str,
    subscription_id: str,
) -> None:
    runner = FakeRunner(
        [
            _result(stdout="{}"),
            _result(stdout="{}"),
            _result(
                stdout=json.dumps(
                    [
                        {
                            "id": (
                                "/subscriptions/id/resourceGroups/group/providers/x/b"
                            ),
                            "name": "resource-b",
                            "type": "Microsoft.Storage/storageAccounts",
                            "location": "eastus2",
                            "resourceGroup": "group",
                            "tags": {"secret-shaped": "excluded"},
                        },
                        {
                            "id": (
                                "/subscriptions/id/resourceGroups/group/providers/x/a"
                            ),
                            "name": "resource-a",
                            "type": "Microsoft.Sql/servers",
                            "location": "eastus",
                            "resourceGroup": "group",
                        },
                    ]
                )
            ),
        ]
    )
    source = AzureResourceSource(runner, "/usr/local/bin/az")

    result = asyncio.run(
        source.lookup(
            target,
            resource_group="group",
            max_results=1,
        )
    )

    assert result["status"] == "ok"
    assert result["subscription_id"] == subscription_id
    assert result["count"] == EXPECTED_RESOURCE_COUNT
    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["records"][0]["name"] == "resource-a"
    assert "tags" not in result["records"][0]
    resource_command = runner.commands[2]
    assert resource_command[3:5] == ("--subscription", subscription_id)
    assert resource_command[-2:] == ("--resource-group", "group")


def test_azure_source_prompts_for_login_when_cli_has_no_session() -> None:
    runner = FakeRunner([_result(returncode=1)])
    source = AzureResourceSource(runner, "/usr/local/bin/az")

    result = asyncio.run(source.lookup("production"))

    assert result["status"] == "login_required"
    assert result["command"] == "az login"
    assert "browser prompt" in result["message"]
    assert len(runner.commands) == 1


def test_azure_source_prompts_when_identity_cannot_access_subscription() -> None:
    runner = FakeRunner([_result(stdout="{}"), _result(returncode=1)])
    source = AzureResourceSource(runner, "/usr/local/bin/az")

    result = asyncio.run(source.lookup("ra_preprod"))

    assert result["status"] == "subscription_access_required"
    assert result["command"] == "az login"
    assert PREPROD_SUBSCRIPTION in result["message"]
    assert len(runner.commands) == EXPECTED_ACCOUNT_COMMAND_COUNT


def test_azure_source_reports_missing_cli() -> None:
    source = AzureResourceSource(FakeRunner([]), None)

    result = asyncio.run(source.lookup("data_engineering"))

    assert result["status"] == "azure_cli_required"
    assert result["command"] == "az --version"


def test_azure_source_rejects_invalid_inputs() -> None:
    source = AzureResourceSource(FakeRunner([]), None)

    with pytest.raises(AzureResourceError, match="must be one of"):
        asyncio.run(source.lookup("unknown"))
    with pytest.raises(AzureResourceError, match="max_results"):
        asyncio.run(source.lookup("production", max_results=0))


def test_azure_source_rejects_malformed_resource_output() -> None:
    runner = FakeRunner(
        [
            _result(stdout="{}"),
            _result(stdout="{}"),
            _result(stdout="{}"),
        ]
    )
    source = AzureResourceSource(runner, "/usr/local/bin/az")

    with pytest.raises(AzureResourceError, match="invalid JSON"):
        asyncio.run(source.lookup("production"))
