"""Prompt templates for benchmark model matrices."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from workspaces.data_engineering.agents.production_support.templates import (
    HUMAN_IDENTITY_ACTION_TEMPLATE,
    RESEND_ACTION_TEMPLATE,
)
from workspaces.data_engineering.benchmarks.handoff_contracts import HandoffContract
from workspaces.data_engineering.benchmarks.matrix_evidence import (
    compact_brief_shell_command,
)


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

    @property
    def handoff_contract(self) -> HandoffContract | None:
        """Return the named-agent handoff contract, when configured."""
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
    if manifest.handoff_contract is not None and manifest.case_id.startswith(
        "handoff-"
    ):
        return _build_handoff_case_prompt_lines(manifest, profile)
    operational_date = manifest.operational_start.partition("T")[0]
    failure_links = tuple(
        (
            region,
            _task_instance_url(
                base_url,
                manifest.operational_start,
                manifest.operational_end,
            ),
        )
        for region, base_url in manifest.airflow_base_urls
    )
    compact_command = compact_brief_shell_command(manifest)
    if compact_command is None:
        msg = "full production-support case requires compact_brief.py"
        raise ValueError(msg)
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
    handoff_lines = _handoff_prompt_lines(manifest.handoff_contract)
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
        *handoff_lines,
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
        "the complete final report with Developer, Data Internal, and Follow Up "
        "outputs. The Reporting Agent output is authoritative: return it verbatim. "
        "The orchestrator must not rewrite, reconstruct, summarize, repair, or append "
        "to it. If it violates the contract, fail instead of performing a second "
        "reporting pass.",
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
        "validated error under 'For <region> Cluster the following errors exist:'. "
        "Use the source region from errors_by_region and never remap an error based "
        "on client environment, DAG name, or report position. Also return each "
        "selected region's active DAG count and "
        "DAG-processor health from the recorded Airflow handoff. Report the combined "
        "'DAGs parsing properly' line only when both selected regions have healthy "
        "DAG processors and nonzero active counts; never infer parsing health from "
        "the failed-task inventory. For every configured omission candidate, "
        "including D2P and MI3, read the bounded exact failed task log and check "
        "whether the same DAG "
        "and task had a success inside the operational window. Collapse it to an "
        "omission code only when that success is present. Do not query OMS merely to "
        "verify an omission. Retrieve bounded exact evidence for all failures. Query "
        "OMS only for a proven Spark workload when an exact OMS source is supplied.",
        "Resolve every client UUID found in a DAG or task identifier through the "
        "recorded Resource Discovery input before triage or reporting. Use the "
        "resolved name and first three UUID characters in parentheses. When no "
        "unique reviewed name exists, keep 'Unresolved client (<prefix>)' in the "
        "evidence inventory, do not propose a resend or rerun for it, and add this "
        "exact human-help action before any remediation: "
        f"'{HUMAN_IDENTITY_ACTION_TEMPLATE}' Never emit a bare prefix.",
        "Reporting Agent requirements: use one reporting pass only. Group clients "
        "that failed on the same job on one line. If a grouped client has other jobs, "
        "list that client separately with only the other jobs. Mention every "
        "client-job pair exactly once. Put represented omission codes on the final "
        "detail line of each regional Data Internal block. An unverified omission "
        "candidate remains a normal failure with its diagnosis and supported "
        "follow-up.",
        "Never place a CA finding in US or a US finding in CA. Do not describe one "
        "cluster as both healthy and unhealthy from the same evidence. Use no periods "
        "in Data Internal and no blank lines between its bullets.",
        "For every failed DAG, also provide a DAG grid link using this exact shape:",
        "<airflow-base-url>/dags/<dag-id>/grid?status=failed"
        f"&execution_start={manifest.operational_start}"
        f"&execution_end={manifest.operational_end}",
        "Follow Up is an action list, not an investigation summary. Never claim a "
        "rerun, resend, bounce, or other production mutation occurred. Include the "
        "date on every proposed action and return '- No action is required.' when no "
        "supported action exists. The canonical resend action is exactly:",
        f"  - {RESEND_ACTION_TEMPLATE}",
        "Instantiate that template from the report brief without paraphrasing it. "
        "Do not write 'consider resending', 'review', 'investigate', 'before "
        "considering reruns', or generic infrastructure follow-ups. Cluster warnings "
        "such as a retired DAG processor or KEDA read-access limitation remain "
        "Developer evidence and do not create a Follow Up by themselves.",
        "Use case applicability. If OMS, Spark-race, automation, or another optional "
        "source is not supplied or not needed, avoid that work and treat it as "
        "success rather than an evidence gap.",
        "Do not mutate production systems. Return the final report only.",
        *(f"Case requirement: {item}" for item in manifest.case_instructions),
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


def _task_instance_url(base_url: str, start: str, end: str) -> str:
    query = urlencode(
        (
            ("_flt_3_state", "failed"),
            ("_flt_2_end_date", _airflow_ui_datetime(start)),
            ("_flt_1_end_date", _airflow_ui_datetime(end)),
        )
    )
    return f"{base_url}/taskinstance/list/?{query}#"


def _airflow_ui_datetime(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    hour = parsed.strftime("%I").lstrip("0") or "0"
    return f"{parsed:%m/%d/%Y} {hour}:{parsed:%M} {parsed:%p}"


def _handoff_prompt_lines(contract: HandoffContract | None) -> tuple[str, ...]:
    if contract is None:
        return ()
    lines = [
        "This case has an explicit named-agent handoff contract.",
        f"Use no more than {contract.max_parallel} concurrent handoffs.",
    ]
    lines.extend(
        (
            f"- {agent.parent} -> {agent.name}: "
            f"calls={agent.min_calls}..{agent.max_calls}; "
            f"starts_after={','.join(agent.starts_after) or 'none'}; "
            f"inputs={','.join(agent.required_input_fields) or 'none'}; "
            f"outputs={','.join(agent.required_output_fields) or 'none'}; "
            f"mode={agent.expected_mode}; "
            f"can_delegate={str(agent.can_delegate).lower()}"
        )
        for agent in contract.agents
    )
    if contract.output_authority is not None:
        lines.append(
            f"{contract.output_authority} is the authoritative final-output handoff."
        )
    return tuple(lines)


def _build_handoff_case_prompt_lines(
    manifest: MatrixPromptManifest,
    profile: MatrixPromptProfile,
) -> list[str]:
    return [
        "Run the named-agent production-support handoff benchmark.",
        f"Case: {manifest.case_id}",
        f"User request: {manifest.case_prompt}",
        f"Dataset: {manifest.dataset}",
        "Additional recorded inputs: "
        f"{', '.join(map(str, manifest.candidate_inputs)) or 'none'}",
        f"Operational window: {manifest.operational_start} to "
        f"{manifest.operational_end}",
        f"Your role: {profile.role}.",
        *_handoff_prompt_lines(manifest.handoff_contract),
        "Requirements:",
        *(f"- {item}" for item in manifest.case_instructions),
        "Use only local recorded evidence. Do not access hidden expectations.",
        "Do not mutate production. FollowUp retry cases must remain plan-only.",
        "Return the requested operational output even when benchmark artifacts "
        "are also built.",
    ]
