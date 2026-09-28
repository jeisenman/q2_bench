from pathlib import Path
from typing import Any

import yaml

BENCHMARK_ROOT = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks/resource_discovery"
)
EXPECTED_CONVERSATIONS = 2
EXPECTED_CONFIRMATION_THRESHOLD = 3


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one benchmark YAML mapping."""
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_resource_discovery_manifest_declares_a_typed_benchmark() -> None:
    manifest = load_yaml(BENCHMARK_ROOT / "manifest.yaml")

    assert manifest["schema_version"] == 1
    assert str(manifest["benchmark_id"]).startswith("data_engineering.")
    assert manifest["display_name"]
    assert manifest["version"]
    assert manifest["group"]
    assert manifest["description"]
    assert "evaluation" in manifest


def test_resource_discovery_suite_defines_opaque_synthetic_cases() -> None:
    suite_root = BENCHMARK_ROOT
    suite = load_yaml(suite_root / "suite.yaml")
    cases = load_yaml(suite_root / "cases.yaml")
    assert suite["schema_version"] == 1
    assert suite["benchmark_id"]
    assert set(suite["layers"]) >= {"capabilities", "system"}
    assert [case["id"] for case in cases["cases"]] == [
        "case-001",
        "case-002",
        "case-003",
        "case-004",
    ]
    assert all(
        (suite_root / case_id / "asset.json").is_file()
        and (suite_root / case_id / "capability.yaml").is_file()
        for case_id in suite["system_cases"]
    )


def test_public_assets_and_hidden_expectations_are_disjoint() -> None:
    suite_root = BENCHMARK_ROOT
    manifest = load_yaml(BENCHMARK_ROOT / "manifest.yaml")
    suite = load_yaml(suite_root / "suite.yaml")

    public_paths = set(manifest.get("public_assets", ()))
    public_paths.update(suite.get("public_assets", ()))
    hidden_paths = {
        "hidden/expected_results.yaml",
        "hidden/resource_query_rubric.yaml",
        "hidden/alias_memory_rubric.yaml",
    }

    assert public_paths
    assert hidden_paths
    assert public_paths.isdisjoint(hidden_paths)
    assert all((suite_root / path).is_file() for path in public_paths)
    assert all((suite_root / path).is_file() for path in hidden_paths)
    assert all("hidden" not in path.split("/") for path in public_paths)


def test_public_case_metadata_does_not_name_hidden_expectations_or_secrets() -> None:
    suite_root = BENCHMARK_ROOT
    manifest = load_yaml(BENCHMARK_ROOT / "manifest.yaml")
    suite = load_yaml(suite_root / "suite.yaml")
    public_case_and_fixture_text = "\n".join(
        (
            (suite_root / "cases.yaml").read_text(encoding="utf-8"),
            *(
                path.read_text(encoding="utf-8")
                for path in suite_root.glob("case-*/capability.yaml")
            ),
            *(
                path.read_text(encoding="utf-8")
                for path in suite_root.glob("case-*/asset.json")
            ),
        )
    ).lower()

    hidden_paths = set(manifest.get("hidden_expectations", ()))
    hidden_paths.update(suite.get("hidden_expectations", ()))
    for hidden_path in hidden_paths:
        assert hidden_path.lower() not in public_case_and_fixture_text
    for secret_marker in ("client_secret", "access_token", "refresh_token"):
        assert secret_marker not in public_case_and_fixture_text


def test_alias_memory_suite_requires_repeated_cross_conversation_evidence() -> None:
    suite_root = BENCHMARK_ROOT
    suite = load_yaml(suite_root / "suite.yaml")
    cases = load_yaml(suite_root / "cases.yaml")
    expected = load_yaml(suite_root / "hidden" / "expected_results.yaml")

    case = cases["cases"][3]
    expectation = expected["cases"][3]

    assert suite["system_cases"][-1] == "case-004"
    assert (suite_root / "case-004" / "asset.json").is_file()
    assert (suite_root / "case-004" / "capability.yaml").is_file()
    assert len(case["conversations"]) == EXPECTED_CONVERSATIONS
    assert expectation["initial_memory_count"] == 0
    assert expectation["confirmation_threshold"] == EXPECTED_CONFIRMATION_THRESHOLD
    assert expectation["expected_memory"]["evidence_count"] == 1
    assert expectation["expected_memory"]["status"] == "proposed"
    assert expectation["expected_events"][-1]["status"] == "confirmation_required"
