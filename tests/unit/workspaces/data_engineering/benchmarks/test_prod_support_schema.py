from pathlib import Path

import yaml

ROOT = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks"
    / "production_support/dates"
)
SNAPSHOTS = (ROOT / "09-25-26", ROOT / "09-26-26")
V2_SNAPSHOT = ROOT / "09-26-26-v2"
ALL_SNAPSHOTS = (*SNAPSHOTS, V2_SNAPSHOT)
EXPECTED_CAPTURE_RECORDS = 65
EXPECTED_IN_WINDOW_FAILURES = 50
EXPECTED_MCP_FAILURES = 22
EXPECTED_TRACE_FAILURES = 23
EXPECTED_NOT_ACCESSED_FAILURES = 27


def _load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _schema(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _schema(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        item_schemas = tuple(_schema(item) for item in value)
        if not item_schemas:
            return ("list", ())
        first = item_schemas[0]
        assert all(item == first for item in item_schemas)
        return ("list", first)
    return type(value).__name__


def test_capability_snapshots_have_identical_file_and_document_schemas() -> None:
    capability_sets = tuple(
        {path.name for path in (snapshot / "capabilities").glob("*.yaml")}
        for snapshot in ALL_SNAPSHOTS
    )

    assert all(items == capability_sets[0] for items in capability_sets[1:])
    for filename in sorted(capability_sets[0]):
        schemas = tuple(
            _schema(_load(snapshot / "capabilities" / filename))
            for snapshot in ALL_SNAPSHOTS
        )
        assert all(item == schemas[0] for item in schemas[1:]), filename


def test_suite_snapshots_register_identical_capability_contracts() -> None:
    suites = tuple(_load(snapshot / "suite.yaml") for snapshot in ALL_SNAPSHOTS)
    assert all(isinstance(item, dict) for item in suites)
    assert all(_schema(item) == _schema(suites[0]) for item in suites[1:])
    layers = tuple(item["layers"] for item in suites)
    assert all(
        item["capabilities"]["fixtures"] == layers[0]["capabilities"]["fixtures"]
        for item in layers[1:]
    )
    assert all(
        item["capabilities"]["dimensions"] == layers[0]["capabilities"]["dimensions"]
        for item in layers[1:]
    )
    assert all(
        item["coordination"]["dimensions"] == layers[0]["coordination"]["dimensions"]
        for item in layers[1:]
    )


def test_snapshots_share_report_configuration_and_output_contracts() -> None:
    expected_groups = ["d2p", "mi3", "subscriber", "maintenance", "backfill", "cmm"]
    configurations = tuple(
        _load(snapshot / "capabilities" / "report_configuration.yaml")
        for snapshot in ALL_SNAPSHOTS
    )
    expectations = tuple(
        _load(snapshot / "hidden" / "case_expectations.yaml")
        for snapshot in ALL_SNAPSHOTS
    )
    cases = (
        expectations[0]["cases"][0],
        expectations[1],
        expectations[2],
    )

    assert all(item == configurations[0] for item in configurations[1:])
    assert configurations[0]["cases"][0]["default_groups"] == expected_groups
    assert all(
        set(item["required_output_format"]) == set(cases[0]["required_output_format"])
        for item in cases[1:]
    )
    assert all(item["omitted_from_data_internal"] == expected_groups for item in cases)
    assert all(
        item["required_output_format"]["developer_cluster_health_position"] == "first"
        for item in cases
    )
    assert all(
        item["required_output_format"]["prohibit_cross_region_findings"] is True
        for item in cases
    )
    assert all(
        item["required_output_format"]["prohibit_cluster_status_contradictions"] is True
        for item in cases
    )


def test_prod_support_suite_defines_three_evaluation_layers() -> None:
    suite = _load(SNAPSHOTS[0] / "suite.yaml")

    assert isinstance(suite, dict)
    assert suite["suite_date"] == "2026-09-25"
    assert set(suite["layers"]) == {"capabilities", "coordination", "system"}
    assert "diagnosis_accuracy" in suite["layers"]["capabilities"]["dimensions"]
    assert "evidence_handoff" in suite["layers"]["coordination"]["dimensions"]
    assert "prod-support-us-ca-2026-09-25" in suite["layers"]["system"]["cases"]


def test_september_26_v2_holistic_mcp_evidence_contract() -> None:
    public_cases = _load(V2_SNAPSHOT / "cases.yaml")
    expectations = _load(V2_SNAPSHOT / "hidden" / "case_expectations.yaml")
    suite = _load(V2_SNAPSHOT / "suite.yaml")

    case_id = "prod-support-us-ca-operational-2026-09-25-v2"
    assert public_cases["cases"][0]["id"] == case_id
    assert expectations["case_id"] == case_id
    assert suite["layers"]["system"]["cases"] == [case_id]

    contract = expectations["mcp_result_contract"]
    assert "follow_up" in contract["required_fields"]
    assert contract["follow_up_field"] == "follow_up"
    assert contract["follow_up_in_output"] is True
    assert contract["follow_up_source"] == "mcp"

    evidence = _load(V2_SNAPSHOT / "evidence" / "mcp_debug_source.yaml")
    assert evidence["source"] == "production_mcp_debug"
    assert (
        evidence["artifacts"]["airflow_capture"]["record_count"]
        == EXPECTED_CAPTURE_RECORDS
    )
    assert (
        evidence["artifacts"]["airflow_capture"]["in_window_count"]
        == EXPECTED_IN_WINDOW_FAILURES
    )
    assert evidence["artifacts"]["mcp_result"]["failure_count"] == EXPECTED_MCP_FAILURES
    assert evidence["artifacts"]["mcp_result"]["follow_up_present"] is True
    assert expectations["mcp_debug_evidence"]["require_follow_up"] is True

    holistic = expectations["holistic_evidence"]
    assert holistic["captured_failure_count"] == EXPECTED_IN_WINDOW_FAILURES
    assert holistic["agent_accessed_failure_count"] == EXPECTED_TRACE_FAILURES
    assert (
        holistic["agent_not_accessed_failure_count"] == EXPECTED_NOT_ACCESSED_FAILURES
    )
    assert holistic["null_means_not_accessed"] is True
    assert holistic["prohibit_null_as_negative_evidence"] is True
    assert (
        evidence["artifacts"]["holistic_evidence"]["source_results"]["oms_job_logs"]
        == "not_accessed"
    )
