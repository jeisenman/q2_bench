"""Read allowlisted Azure resources through an authenticated Azure CLI."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

AZURE_RESOURCE_TARGETS = {
    "ra_preprod": (
        "cde221ff-e7f4-4d39-be20-6f9d532cab60",
        "PrecisionLender PreProd",
    ),
    "data_engineering": (
        "b7b3f313-bcc8-4754-aa71-a8c9a910841c",
        "PrecisionLender DataScience",
    ),
    "production": (
        "71aa0ec0-8411-43a2-9908-ddd2add764eb",
        "PrecisionLender Production",
    ),
}
DEFAULT_MAX_RESULTS = 100
MAX_RESULTS = 500


class AzureResourceError(RuntimeError):
    """Raised when an Azure resource query is invalid or fails."""

    @classmethod
    def invalid_target(cls, target: str) -> AzureResourceError:
        """Return an error for an unknown logical subscription target."""
        allowed = ", ".join(AZURE_RESOURCE_TARGETS)
        return cls(f"Azure target {target!r} must be one of: {allowed}")

    @classmethod
    def invalid_max_results(cls) -> AzureResourceError:
        """Return an error for an unsafe result bound."""
        return cls(f"max_results must be between 1 and {MAX_RESULTS}")

    @classmethod
    def invalid_resource_response(cls) -> AzureResourceError:
        """Return an error for malformed Azure CLI JSON."""
        return cls("Azure CLI returned invalid JSON for resource listing")

    @classmethod
    def resource_listing_failed(cls) -> AzureResourceError:
        """Return an error for a failed authenticated Azure CLI command."""
        return cls("Azure CLI failed while attempting to list resources")


class AzureCommandRunner(Protocol):
    """Execute one Azure CLI command without a shell."""

    def run(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Return the completed Azure CLI process."""
        ...


class SubprocessAzureCommandRunner:
    """Execute Azure CLI commands through the standard library."""

    def run(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Run one bounded non-interactive Azure CLI command."""
        return subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )


@dataclass(frozen=True, slots=True)
class AzureResourceSource:
    """List non-secret Azure resource metadata in an explicit subscription."""

    runner: AzureCommandRunner
    az_path: str | None = None

    @classmethod
    def create(cls) -> AzureResourceSource:
        """Create a source using the Azure CLI found on the current path."""
        return cls(SubprocessAzureCommandRunner(), shutil.which("az"))

    async def lookup(
        self,
        target: str,
        *,
        name: str | None = None,
        resource_group: str | None = None,
        resource_type: str | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> dict[str, object]:
        """Verify login and return bounded allowlisted Azure resources."""
        return await asyncio.to_thread(
            self._lookup,
            target,
            name,
            resource_group,
            resource_type,
            max_results,
        )

    def _lookup(
        self,
        target: str,
        name: str | None,
        resource_group: str | None,
        resource_type: str | None,
        max_results: int,
    ) -> dict[str, object]:
        subscription_id, subscription_name = _subscription(target)
        if not 1 <= max_results <= MAX_RESULTS:
            raise AzureResourceError.invalid_max_results()
        if self.az_path is None:
            return _action_required(
                status="azure_cli_required",
                message="Azure CLI is required before Azure resources can be queried.",
                command="az --version",
                subscription_id=subscription_id,
                subscription_name=subscription_name,
            )
        if self.runner.run(_account_command(self.az_path)).returncode:
            return _action_required(
                status="login_required",
                message=(
                    "Azure CLI login is required. Run `az login`, complete the "
                    "browser prompt, then retry this resource lookup."
                ),
                command="az login",
                subscription_id=subscription_id,
                subscription_name=subscription_name,
            )
        target_account = self.runner.run(
            _account_command(self.az_path, subscription_id)
        )
        if target_account.returncode:
            return _action_required(
                status="subscription_access_required",
                message=(
                    "The active Azure identity cannot access "
                    f"{subscription_name} ({subscription_id}). Run `az login` "
                    "with an identity that has access, then retry."
                ),
                command="az login",
                subscription_id=subscription_id,
                subscription_name=subscription_name,
            )
        command = _resource_command(
            self.az_path,
            subscription_id,
            name=name,
            resource_group=resource_group,
            resource_type=resource_type,
        )
        result = self.runner.run(command)
        if result.returncode:
            raise AzureResourceError.resource_listing_failed()
        records = _resource_records(result.stdout)
        returned = records[:max_results]
        return {
            "status": "ok",
            "message": (
                f"Queried {subscription_name} ({subscription_id}) with "
                f"`{_display_command(command)}`."
            ),
            "command": _display_command(command),
            "target": target,
            "subscription_id": subscription_id,
            "subscription_name": subscription_name,
            "count": len(records),
            "returned_count": len(returned),
            "truncated": len(records) > len(returned),
            "records": returned,
        }


def _subscription(target: str) -> tuple[str, str]:
    try:
        return AZURE_RESOURCE_TARGETS[target]
    except KeyError as error:
        raise AzureResourceError.invalid_target(target) from error


def _account_command(
    az_path: str,
    subscription_id: str | None = None,
) -> tuple[str, ...]:
    command = [
        az_path,
        "account",
        "show",
        "--output",
        "json",
        "--only-show-errors",
    ]
    if subscription_id is not None:
        command.extend(("--subscription", subscription_id))
    return tuple(command)


def _resource_command(
    az_path: str,
    subscription_id: str,
    *,
    name: str | None,
    resource_group: str | None,
    resource_type: str | None,
) -> tuple[str, ...]:
    command = [
        az_path,
        "resource",
        "list",
        "--subscription",
        subscription_id,
        "--output",
        "json",
        "--only-show-errors",
    ]
    for option, value in (
        ("--name", name),
        ("--resource-group", resource_group),
        ("--resource-type", resource_type),
    ):
        if value is not None and value.strip():
            command.extend((option, value))
    return tuple(command)


def _resource_records(payload: str) -> tuple[dict[str, object], ...]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as error:
        raise AzureResourceError.invalid_resource_response() from error
    if not isinstance(decoded, list) or not all(
        isinstance(item, Mapping) for item in decoded
    ):
        raise AzureResourceError.invalid_resource_response()
    records = tuple(_safe_resource(item) for item in decoded)
    return tuple(sorted(records, key=_resource_sort_key))


def _safe_resource(resource: Mapping[str, object]) -> dict[str, object]:
    aliases = {
        "resourceGroup": "resource_group",
        "subscriptionId": "subscription_id",
    }
    record: dict[str, object] = {}
    for source_name in (
        "id",
        "name",
        "type",
        "kind",
        "location",
        "resourceGroup",
        "subscriptionId",
    ):
        value = resource.get(source_name)
        if isinstance(value, str) and value.strip():
            record[aliases.get(source_name, source_name)] = value
    return record


def _resource_sort_key(record: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(record.get("resource_group", "")).casefold(),
        str(record.get("type", "")).casefold(),
        str(record.get("name", "")).casefold(),
    )


def _action_required(
    *,
    status: str,
    message: str,
    command: str,
    subscription_id: str,
    subscription_name: str,
) -> dict[str, object]:
    return {
        "status": status,
        "message": message,
        "command": command,
        "subscription_id": subscription_id,
        "subscription_name": subscription_name,
        "count": 0,
        "returned_count": 0,
        "truncated": False,
        "records": [],
    }


def _display_command(command: Sequence[str]) -> str:
    return " ".join(("az", *command[1:]))
