"""Prompt templates for benchmark model matrices."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class MatrixPromptManifest(Protocol):
    """Matrix values required by the production-support prompt."""

    @property
    def case_id(self) -> str:
        """Return the selected case identifier."""
        ...

    @property
    def dataset(self) -> Path:
        """Return the primary recorded dataset."""
        ...

    @property
    def candidate_inputs(self) -> tuple[Path, ...]:
        """Return additional recorded candidate inputs."""
        ...

    @property
    def airflow_base_urls(self) -> tuple[tuple[str, str], ...]:
        """Return regional Airflow base URLs."""
        ...

    @property
    def operational_start(self) -> str:
        """Return the operational-window start."""
        ...

    @property
    def operational_end(self) -> str:
        """Return the operational-window end."""
        ...

    @property
    def capability(self) -> str | None:
        """Return the isolated capability name, when configured."""
        ...

    @property
    def case_prompt(self) -> str:
        """Return the focused case task."""
        ...

    @property
    def case_instructions(self) -> tuple[str, ...]:
        """Return focused case requirements."""
        ...

    @property
    def applicability(self) -> tuple[tuple[str, bool], ...]:
        """Return criterion applicability declared by the case."""
        ...


class MatrixPromptProfile(Protocol):
    """Model-profile values required by the production-support prompt."""

    @property
    def role(self) -> str:
        """Return the candidate role."""
        ...

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Return the measured candidate capabilities."""
        ...


def build_prod_support_prompt_lines(
    manifest: MatrixPromptManifest,
    profile: MatrixPromptProfile,
) -> list[str]:
    """Build the production-support orchestrator benchmark prompt."""
    operational_date = manifest.operational_start.partition("T")[0]
    failure_links = tuple(
        (
            region,
            f"{base_url}/taskinstance/list/"
            f"?_flt_1_end_date={manifest.operational_end}"
            "&_flt_3_state=failed"
            f"&_flt_2_end_date={manifest.operational_start}#",
        )
        for region, base_url in manifest.airflow_base_urls
    )
    compact_parser = (
        "workspaces.data_engineering.benchmarks.production_support.compact_brief"
    )
    inputs_by_name = {path.name: str(path) for path in manifest.candidate_inputs}
    applicability = dict(manifest.applicability)
    optional_inputs = (
        ("cluster_health_snapshot.json", "--cluster-health", "cluster_health"),
        ("resource_discovery_snapshot.json", "--resource-discovery", None),
        (
            "multi_run_log_fallback.json",
            "--prior-run-logs",
            "prior_run_log_fallback",
        ),
        ("relationship_signals_prior_day.json", "--prior-context", None),
    )
    optional_arguments = " ".join(
        f"{argument} {inputs_by_name[name]}"
        for name, argument, criterion in optional_inputs
        if name in inputs_by_name
        and (criterion is None or applicability.get(criterion, True))
    )
    compact_command = (
        f"PYTHONPATH=src python3 -m {compact_parser} --dataset {manifest.dataset} "
        f"--start {manifest.operational_start} --end {manifest.operational_end} "
        f"{optional_arguments} "
        "--output /tmp/prod-support-compact-evidence.json"
    )
    region_labels = tuple(region.partition("-")[0] for region, _ in failure_links)
    developer_health = tuple(
        f"  - {label} Cluster Health: <pod state, restart count, and KEDA health>"
        for label in region_labels
    )
    data_internal_regions = tuple(
        line
        for label in region_labels
        for line in (
            label,
            "- Good|Ongoing",
            "  - <grouped client and job failures>",
            "  - <represented omission codes, always last>",
        )
    )
    return [
        "Run the prod-support benchmark using only local recorded evidence.",
        f"Case: {manifest.case_id}",
        f"User request: {manifest.case_prompt or 'Do prod support'}",
        f"Dataset: {manifest.dataset}",
        "Additional recorded inputs: "
        f"{', '.join(map(str, manifest.candidate_inputs)) or 'none'}",
        "Airflow base URLs: "
        + ", ".join(f"{region}={url}" for region, url in manifest.airflow_base_urls),
        f"Your role: {profile.role}.",
        f"Your measured capabilities: {', '.join(profile.capabilities) or 'all'}.",
        "All Cluster, Airflow, identity, and reporting operations are read-only.",
        "Act as the top-level production-support orchestrator. Resolve the requested "
        "date and regional scope first. A generic request selects both regions; "
        "US and CA requests select only that region. When no date is supplied, use "
        "the previous operational day.",
        "The orchestration boundary is fixed:",
        "1. Start one Cluster Agent handoff and one Airflow Agent handoff "
        "concurrently.",
        "2. Cluster and Airflow are leaf agents. They must not spawn, hand off to, "
        "or invoke another agent.",
        "3. The Airflow Agent may query selected regions concurrently with ordinary "
        "I/O concurrency; those regional calls are not additional agents.",
        "4. After both handoffs complete, make one Reporting Agent pass that produces "
        "Developer, Data Internal, and Follow Up outputs.",
        "Final response structure is strict. The first line must be exactly:",
        f"# Prod Support Report — {operational_date} operational day",
        "The next non-empty line must be exactly:",
        (
            "Window: "
            f"`{manifest.operational_start.replace('T', ' ').removesuffix('Z')} UTC` "
            "through "
            f"`{manifest.operational_end.replace('T', ' ').removesuffix('Z')} UTC`"
        ),
        "Do not emit analysis, a preamble, or tool commentary before those lines.",
        "Use exactly one reusable evidence command to replay the Cluster and Airflow "
        "handoffs:",
        compact_command,
        "The command prints one bounded report-ready brief. Use that stdout directly. "
        "Do not reopen inputs or outputs, invoke jq, run another shell command, print "
        "record inventories, raw logs, or an execution JSONL transcript.",
        "Use these exact regional failure-list links without percent encoding or "
        "locale-specific date formatting:",
        *(f"- {region}: {link}" for region, link in failure_links),
        "After the capture summary, use this compact section order:",
        "URLs to validate",
        *(link for _, link in failure_links),
        "",
        "Message for developer:",
        *developer_health,
        "  - <grouped clients and direct error evidence>",
        "",
        f":bangbang: PROD SUPPORT {operational_date} :bangbang:",
        *data_internal_regions,
        "",
        "Follow Ups:",
        "- <suggestion-only action with operational date, or No action is required>",
        "Cluster Agent requirements: report selected-region pod readiness/state, "
        "total restart count, KEDA health, warnings, and evidence gaps. Do not require "
        "DAG parsing or OMS evidence to establish Kubernetes/KEDA health.",
        "Airflow Agent requirements: return every selected-region failure and direct "
        "validated error. D2P and MI3 are registered triage omissions: retain them in "
        "the inventory, but do not fetch task logs or query OMS for them. Retrieve "
        "bounded exact evidence for other failures. Query OMS only for a proven Spark "
        "workload when an exact OMS source is supplied.",
        "Resolve every client UUID found in a DAG or task identifier through the "
        "recorded Resource Discovery input before triage or reporting. Use the "
        "resolved name and first three UUID characters in parentheses. When no "
        "unique reviewed name exists, use 'Unresolved client (<prefix>)'; never "
        "emit a bare prefix.",
        "Reporting Agent requirements: use one reporting pass only. Group clients "
        "that failed on the same job on one line. If a grouped client has other jobs, "
        "list that client separately with only the other jobs. Mention every "
        "client-job pair exactly once. Put represented omission codes on the final "
        "detail line of each regional Data Internal block.",
        "Never place a CA finding in US or a US finding in CA. Do not describe one "
        "cluster as both healthy and unhealthy from the same evidence. Use no periods "
        "in Data Internal and no blank lines between its bullets.",
        "For every failed DAG, also provide a DAG grid link using this exact shape:",
        "<airflow-base-url>/dags/<dag-id>/grid?status=failed"
        f"&execution_start={manifest.operational_start}"
        f"&execution_end={manifest.operational_end}",
        "Follow Up is suggestion-only. Never claim a rerun, resend, bounce, or other "
        "production mutation occurred. Include the operational date on any proposed "
        "action and return 'No action is required' when no supported action exists.",
        "Use case applicability. If OMS, Spark-race, automation, or another optional "
        "source is not supplied or not needed, avoid that work and treat it as "
        "success rather than an evidence gap.",
        "Do not mutate production systems. Return the final report only.",
    ]


def build_capability_prompt_lines(
    manifest: MatrixPromptManifest,
    profile: MatrixPromptProfile,
) -> list[str]:
    """Build a prompt that evaluates exactly one declared capability."""
    if manifest.capability is None:
        msg = "capability prompt requires an isolated capability"
        raise ValueError(msg)
    lines = [
        "Run the prod-bench capability evaluation using only local recorded evidence.",
        f"Case: {manifest.case_id}",
        f"Capability under test: {manifest.capability}",
        f"Dataset: {manifest.dataset}",
        "Additional recorded inputs: "
        f"{', '.join(map(str, manifest.candidate_inputs)) or 'none'}",
        f"Your role: {profile.role}.",
        f"Task: {manifest.case_prompt}",
    ]
    if manifest.airflow_base_urls:
        lines.append(
            "Airflow base URLs: "
            + ", ".join(f"{region}={url}" for region, url in manifest.airflow_base_urls)
        )
    lines.extend(
        (
            "Requirements:",
            *(f"- {item}" for item in manifest.case_instructions),
            "Evaluate only the named capability. Do not produce the complete "
            "prod-support report or investigate unrelated capabilities.",
            "Use read-only operations and do not mutate production systems.",
            "Return only the requested result.",
        )
    )
    return lines
