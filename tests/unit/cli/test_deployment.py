import base64
import json

import pytest
from click.testing import CliRunner

from cli.deployment import (
    ApprovalRequest,
    DeploymentApprovalError,
    approve_deployment,
    approve_pipeline_approval,
)

APPROVAL_ID = 42
DEFAULT_TIMEOUT = 30


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


def test_approve_pipeline_approval_sends_exact_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        assert timeout == DEFAULT_TIMEOUT
        requests.append(request)
        return FakeResponse()

    monkeypatch.setattr("cli.deployment.urlopen", fake_urlopen)

    result = approve_pipeline_approval(
        ApprovalRequest(
            approval_id=APPROVAL_ID,
            organization="precisionlender",
            project="Data Engineering",
            pat="secret-pat",
            comment="Reviewed Alpha deployment.",
        )
    )

    request = requests[0]
    body = json.loads(request.data.decode("utf-8"))
    assert result.approval_id == APPROVAL_ID
    assert result.status == "approved"
    assert request.method == "PATCH"
    assert request.full_url == (
        "https://dev.azure.com/precisionlender/Data%20Engineering/"
        "_apis/pipelines/approvals?api-version=7.1"
    )
    assert body == [
        {
            "approvalId": APPROVAL_ID,
            "status": "approved",
            "comment": "Reviewed Alpha deployment.",
        }
    ]
    assert request.get_header("Authorization") == (
        "Basic " + base64.b64encode(b":secret-pat").decode("ascii")
    )


def test_approve_pipeline_approval_rejects_invalid_inputs() -> None:
    with pytest.raises(DeploymentApprovalError, match="at least 1"):
        approve_pipeline_approval(
            ApprovalRequest(
                approval_id=0,
                organization="org",
                project="project",
                pat="pat",
                comment="comment",
            )
        )

    with pytest.raises(DeploymentApprovalError, match="AZDO_PAT"):
        approve_pipeline_approval(
            ApprovalRequest(
                approval_id=1,
                organization="org",
                project="project",
                pat=" ",
                comment="comment",
            )
        )


def test_approve_deployment_requires_pat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZDO_PAT", raising=False)
    result = CliRunner().invoke(approve_deployment, ["42"])

    assert result.exit_code != 0
    assert "AZDO_PAT" in result.output


def test_approve_deployment_reports_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZDO_PAT", "secret-pat")

    def fake_approve(*_args: object, **_kwargs: object) -> object:
        return type(
            "Result",
            (),
            {"approval_id": APPROVAL_ID, "status": "approved"},
        )()

    monkeypatch.setattr(
        "cli.deployment.approve_pipeline_approval",
        fake_approve,
    )

    result = CliRunner().invoke(
        approve_deployment,
        [str(APPROVAL_ID)],
    )

    assert result.exit_code == 0
    assert result.output == f"approval_id\t{APPROVAL_ID}\nstatus\tapproved\n"
    assert "secret-pat" not in result.output
