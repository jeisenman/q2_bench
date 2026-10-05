"""Commands for explicit deployment approval actions."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import click

DEFAULT_AZDO_ORGANIZATION = "precisionlender"
DEFAULT_AZDO_PROJECT = "Data Engineering"
AZDO_PAT_ENVIRONMENT = "AZDO_PAT"
AZDO_APPROVALS_API_VERSION = "7.1"


class DeploymentApprovalError(RuntimeError):
    """Raised when an Azure DevOps approval cannot be updated."""

    @classmethod
    def invalid_approval_id(cls) -> DeploymentApprovalError:
        """Create an error for an invalid approval identifier."""
        return cls("approval_id must be at least 1")

    @classmethod
    def missing_pat(cls) -> DeploymentApprovalError:
        """Create an error for a missing personal access token."""
        return cls(f"{AZDO_PAT_ENVIRONMENT} must not be empty")

    @classmethod
    def empty_comment(cls) -> DeploymentApprovalError:
        """Create an error for an empty audit comment."""
        return cls("comment must not be empty")

    @classmethod
    def invalid_timeout(cls) -> DeploymentApprovalError:
        """Create an error for an invalid network timeout."""
        return cls("timeout must be at least 1 second")

    @classmethod
    def rejected(cls, approval_id: int, status_code: int) -> DeploymentApprovalError:
        """Create an error for an HTTP rejection."""
        return cls(
            f"Azure DevOps rejected approval {approval_id} with HTTP {status_code}"
        )

    @classmethod
    def unreachable(cls, reason: str) -> DeploymentApprovalError:
        """Create an error for an unreachable Azure DevOps endpoint."""
        return cls(f"could not reach Azure DevOps: {reason}")


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """Summarize one updated deployment approval."""

    approval_id: int
    status: str


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Describe one exact Azure DevOps approval mutation."""

    approval_id: int
    organization: str
    project: str
    pat: str
    comment: str
    timeout: int = 30


def approve_pipeline_approval(approval_request: ApprovalRequest) -> ApprovalResult:
    """Approve one Azure DevOps pipeline approval by its exact ID."""
    if approval_request.approval_id < 1:
        raise DeploymentApprovalError.invalid_approval_id()
    if not approval_request.pat.strip():
        raise DeploymentApprovalError.missing_pat()
    if not approval_request.comment.strip():
        raise DeploymentApprovalError.empty_comment()
    if approval_request.timeout < 1:
        raise DeploymentApprovalError.invalid_timeout()

    url = (
        f"https://dev.azure.com/{quote(approval_request.organization, safe='')}/"
        f"{quote(approval_request.project, safe='')}/_apis/pipelines/approvals"
        f"?api-version={AZDO_APPROVALS_API_VERSION}"
    )
    payload = json.dumps(
        [
            {
                "approvalId": approval_request.approval_id,
                "status": "approved",
                "comment": approval_request.comment,
            }
        ]
    ).encode("utf-8")
    authorization = base64.b64encode(f":{approval_request.pat}".encode()).decode(
        "ascii"
    )
    http_request = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="PATCH",
    )
    try:
        with urlopen(http_request, timeout=approval_request.timeout) as response:
            response.read()
    except HTTPError as error:
        raise DeploymentApprovalError.rejected(
            approval_request.approval_id, error.code
        ) from error
    except URLError as error:
        raise DeploymentApprovalError.unreachable(str(error.reason)) from error
    return ApprovalResult(approval_id=approval_request.approval_id, status="approved")


@click.command("approve-deployment")
@click.argument("approval_id", type=click.IntRange(min=1))
@click.option(
    "--organization",
    default=DEFAULT_AZDO_ORGANIZATION,
    show_default=True,
    help="Azure DevOps organization.",
)
@click.option(
    "--project",
    default=DEFAULT_AZDO_PROJECT,
    show_default=True,
    help="Azure DevOps project.",
)
@click.option(
    "--comment",
    default="Approved via agentbench.",
    show_default=True,
    help="Audit comment recorded with the approval.",
)
def approve_deployment(
    approval_id: int,
    organization: str,
    project: str,
    comment: str,
) -> None:
    """Approve exactly one pending Azure DevOps deployment approval."""
    try:
        result = approve_pipeline_approval(
            ApprovalRequest(
                approval_id=approval_id,
                organization=organization,
                project=project,
                pat=configured_pat(),
                comment=comment,
            )
        )
    except DeploymentApprovalError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"approval_id\t{result.approval_id}")
    click.echo(f"status\t{result.status}")


def configured_pat() -> str:
    """Return the configured Azure DevOps PAT for programmatic callers."""
    return os.environ.get(AZDO_PAT_ENVIRONMENT, "")
