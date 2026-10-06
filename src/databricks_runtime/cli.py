"""Execute Databricks SDK operations requested by the Go MCP API."""

from __future__ import annotations

import json
import sys
from typing import Any

from adapters.databricks import (
    DatabricksRunRequest,
    submit_databricks_run,
    upload_integration_branch,
)

EXPECTED_ARGUMENT_COUNT = 2
INPUT_OBJECT_ERROR = "Databricks runtime input must be a JSON object"
OPTIONS_OBJECT_ERROR = "options must be an object"
USAGE = "usage: python -m databricks_runtime.cli run|upload"


def _payload() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise TypeError(INPUT_OBJECT_ERROR)
    return value


def _run(value: dict[str, Any]) -> dict[str, object]:
    options = value.get("options") or {}
    if not isinstance(options, dict):
        raise TypeError(OPTIONS_OBJECT_ERROR)
    submitted = submit_databricks_run(
        DatabricksRunRequest(
            platform=str(value.get("platform", "")),
            source=str(value.get("source", "")),
            source_sha256=str(value.get("source_sha256", "")),
            existing_cluster_id=str(value.get("existing_cluster_id", "")),
            run_name=str(options.get("run_name", "remote-data-mcp")),
            timeout_seconds=int(options.get("timeout_seconds", 3_600)),
        )
    )
    return {
        "target": submitted.target,
        "notebook_path": submitted.notebook_path,
        "run_id": submitted.run_id,
        "source_sha256": submitted.source_sha256,
        "status": "submitted",
    }


def _upload(value: dict[str, Any]) -> dict[str, object]:
    uploaded = upload_integration_branch(str(value.get("branch", "")))
    return {
        "branch": uploaded.branch,
        "notebook_path": uploaded.notebook_path,
        "output": uploaded.output,
        "credential_requirements": [
            "DE_DATABRICKS_HOST",
            "DE_DATABRICKS_TOKEN",
        ],
        "status": "uploaded",
    }


def main() -> None:
    """Run one JSON-in/JSON-out Databricks operation."""
    if len(sys.argv) != EXPECTED_ARGUMENT_COUNT or sys.argv[1] not in {"run", "upload"}:
        raise SystemExit(USAGE)
    value = _payload()
    result = _run(value) if sys.argv[1] == "run" else _upload(value)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
