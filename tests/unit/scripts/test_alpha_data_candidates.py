"""Tests for the code-test Alpha data candidate index."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = (
    Path(__file__).parents[3]
    / "src/workspaces/data_engineering/skills/code-test/scripts"
    / "alpha_data_candidates.py"
)


def load_script() -> ModuleType:
    """Load the skill script as an isolated test module."""
    spec = importlib.util.spec_from_file_location("alpha_data_candidates", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_static_evidence_groups_operational_literals(tmp_path: Path) -> None:
    module = load_script()
    repository = tmp_path / "di-pipelines"
    source = repository / "dags/sample.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(
            (
                'job_reference = "BalanceJob"',
                'dataset_name = "Primary/Balances"',
                'dataset_version = "1.2"',
                'source_path = "ClientData/Balances.parquet"',
                'file_format = "parquet"',
                'input_resource = "OperationalADLS"',
                'requested = "NewBalance"',
            )
        ),
        encoding="utf-8",
    )

    evidence = module.extract_static_evidence(
        (source,),
        repository,
        ("NewBalance", "MissingField"),
    )

    assert evidence.job_references == {"BalanceJob"}
    assert evidence.datasets == {"Primary/Balances"}
    assert evidence.versions == {"1.2"}
    assert evidence.paths == {"ClientData/Balances.parquet"}
    assert evidence.formats == {"parquet"}
    assert evidence.resources == {"OperationalADLS"}
    assert evidence.field_occurrences == {
        "MissingField": set(),
        "NewBalance": {"dags/sample.py"},
    }


def test_shortlist_contx_resources_excludes_secrets(tmp_path: Path) -> None:
    module = load_script()
    metadata = tmp_path / "alpha"
    metadata.mkdir()
    (metadata / "application_partitions.json").write_text(
        json.dumps(
            {
                "ApplicationPartitionsMetadata": [
                    {
                        "name": module.DEFAULT_CLIENT_ID,
                        "is_active": True,
                        "application": "precisionlender",
                        "client_group": "Client",
                        "shared_group": "Shared",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (metadata / "datastores.json").write_text(
        json.dumps(
            {
                "DatastoresMetadata": {
                    "instances": [
                        {
                            "name": "alpha-data",
                            "kind": "OperationalADLS",
                            "groups": ["Client"],
                            "host_name": "account",
                            "resource_group_name": "alpha-rg",
                            "secret_reference": "never-return",
                            "user": "never-return",
                        },
                        {
                            "name": "database",
                            "kind": "SqlServer",
                            "groups": ["Client"],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    resources = module.shortlist_contx_resources(
        metadata,
        module.DEFAULT_CLIENT_ID,
        ("OperationalADLS",),
    )

    assert resources == (
        {
            "groups": ["Client"],
            "host_name": "account",
            "kind": "OperationalADLS",
            "name": "alpha-data",
            "resource_group_name": "alpha-rg",
        },
    )


def test_shortlist_contx_resources_requires_client_partition(
    tmp_path: Path,
) -> None:
    module = load_script()
    metadata = tmp_path / "alpha"
    metadata.mkdir()
    (metadata / "application_partitions.json").write_text(
        '{"ApplicationPartitionsMetadata": []}',
        encoding="utf-8",
    )
    (metadata / "datastores.json").write_text(
        '{"DatastoresMetadata": {"instances": []}}',
        encoding="utf-8",
    )

    with pytest.raises(module.AnalysisError, match="partition not found"):
        module.shortlist_contx_resources(metadata, module.DEFAULT_CLIENT_ID)
