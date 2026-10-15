from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

import adapters.databricks.runs as databricks_runs
from adapters.databricks.runs import (
    DatabricksConnection,
    DatabricksRunError,
    DatabricksRunRequest,
    submit_databricks_run,
)

SOURCE = "# Databricks notebook source\n\ndisplay(spark.range(1))\n"
SUBMITTED_RUN_ID = 12345


class FakeDatabricksClient:
    def __init__(self, workspace_id: int) -> None:
        self._workspace_id = workspace_id
        self.imported: tuple[str, str] | None = None
        self.submitted: dict[str, object] | None = None

    def workspace_id(self) -> int:
        return self._workspace_id

    def import_source(self, path: str, source: str) -> None:
        self.imported = (path, source)

    def submit(
        self,
        *,
        notebook_path: str,
        existing_cluster_id: str,
        run_name: str,
        timeout_seconds: int,
    ) -> int:
        self.submitted = {
            "notebook_path": notebook_path,
            "existing_cluster_id": existing_cluster_id,
            "run_name": run_name,
            "timeout_seconds": timeout_seconds,
        }
        return SUBMITTED_RUN_ID


def _write_configuration(
    path: Path,
    *,
    workspace_enabled: bool = True,
    environment_enabled: bool = True,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "workspaces": {
                    "data_engineering": {
                        "enabled": workspace_enabled,
                        "databricks": {
                            "ra": {
                                "enabled": environment_enabled,
                                "auth": "pat",
                                "host_env": "RA_DATABRICKS_HOST",
                                "token_env": "RA_DATABRICKS_TOKEN",
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_submits_exact_reviewed_source_to_verified_workspace(
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "configurations.yaml"
    _write_configuration(configuration)
    fake = FakeDatabricksClient(7628572648057993)
    connections: list[DatabricksConnection] = []

    def factory(connection: DatabricksConnection) -> FakeDatabricksClient:
        connections.append(connection)
        return fake

    digest = hashlib.sha256(SOURCE.encode()).hexdigest()
    result = submit_databricks_run(
        DatabricksRunRequest("ra", SOURCE, digest, "cluster-123"),
        configuration_path=configuration,
        environ={
            "RA_DATABRICKS_HOST": (
                "https://adb-7628572648057993.13.azuredatabricks.net"
            ),
            "RA_DATABRICKS_TOKEN": "secret",
        },
        client_factory=factory,
    )

    expected_path = f"/Shared/remote-data-mcp/ra/{digest}"
    assert connections == [
        DatabricksConnection(
            "https://adb-7628572648057993.13.azuredatabricks.net",
            "secret",
            7628572648057993,
        )
    ]
    assert fake.imported == (expected_path, SOURCE)
    assert fake.submitted == {
        "notebook_path": expected_path,
        "existing_cluster_id": "cluster-123",
        "run_name": "remote-data-mcp",
        "timeout_seconds": 3600,
    }
    assert result.run_id == SUBMITTED_RUN_ID
    assert result.target == "pl-databricks-us-rapreprod-01"
    assert result.source_sha256 == digest


def test_sdk_client_uses_configured_workspace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeWorkspaceClient:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(databricks_runs, "WorkspaceClient", FakeWorkspaceClient)

    databricks_runs.SdkDatabricksRunClient(
        DatabricksConnection("https://example.databricks.net", "secret", 12345)
    )

    assert calls == [
        {
            "host": "https://example.databricks.net",
            "token": "secret",
            "auth_type": "pat",
            "workspace_id": 12345,
            "product": "q2-bench",
        }
    ]


@pytest.mark.parametrize(
    ("workspace_enabled", "environment_enabled", "message"),
    [
        (False, True, "workspaces.data_engineering.enabled must be true"),
        (True, False, "databricks.ra.enabled must be true"),
    ],
)
def test_rejects_disabled_configuration(
    tmp_path: Path,
    workspace_enabled: bool,
    environment_enabled: bool,
    message: str,
) -> None:
    configuration = tmp_path / "configurations.yaml"
    _write_configuration(
        configuration,
        workspace_enabled=workspace_enabled,
        environment_enabled=environment_enabled,
    )

    with pytest.raises(DatabricksRunError, match=message):
        submit_databricks_run(
            DatabricksRunRequest(
                "ra",
                SOURCE,
                hashlib.sha256(SOURCE.encode()).hexdigest(),
                "cluster-123",
            ),
            configuration_path=configuration,
            environ={},
        )


def test_rejects_source_changed_after_review(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    _write_configuration(configuration)

    with pytest.raises(DatabricksRunError, match="does not match source"):
        submit_databricks_run(
            DatabricksRunRequest(
                "ra",
                SOURCE + "display(spark.range(2))\n",
                hashlib.sha256(SOURCE.encode()).hexdigest(),
                "cluster-123",
            ),
            configuration_path=configuration,
            environ={},
        )


def test_rejects_credentials_for_another_workspace(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    _write_configuration(configuration)
    fake = FakeDatabricksClient(3510128597187204)

    with pytest.raises(DatabricksRunError, match="expected 7628572648057993"):
        submit_databricks_run(
            DatabricksRunRequest(
                "ra",
                SOURCE,
                hashlib.sha256(SOURCE.encode()).hexdigest(),
                "cluster-123",
            ),
            configuration_path=configuration,
            environ={
                "RA_DATABRICKS_HOST": "https://example.databricks.net",
                "RA_DATABRICKS_TOKEN": "secret",
            },
            client_factory=lambda _: fake,
        )

    assert fake.imported is None


def test_rejects_ambiguous_databricks_environment_variables(
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "configurations.yaml"
    _write_configuration(configuration)

    with pytest.raises(DatabricksRunError, match="ambiguous DATABRICKS_HOST"):
        submit_databricks_run(
            DatabricksRunRequest(
                "ra",
                SOURCE,
                hashlib.sha256(SOURCE.encode()).hexdigest(),
                "cluster-123",
            ),
            configuration_path=configuration,
            environ={"DATABRICKS_HOST": "https://wrong.example"},
        )
