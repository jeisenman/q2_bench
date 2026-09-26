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
    """Build the strict production-support candidate prompt lines."""
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
    return [
        "Run the prod-support benchmark using only local recorded evidence.",
        f"Case: {manifest.case_id}",
        f"Dataset: {manifest.dataset}",
        "Additional recorded inputs: "
        f"{', '.join(map(str, manifest.candidate_inputs)) or 'none'}",
        "Airflow base URLs: "
        + ", ".join(f"{region}={url}" for region, url in manifest.airflow_base_urls),
        f"Your role: {profile.role}.",
        f"Your measured capabilities: {', '.join(profile.capabilities) or 'all'}.",
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
        "Start with exactly one reusable evidence command:",
        "agentbench summarize-prod-support-evidence "
        f"--dataset {manifest.dataset} --start {manifest.operational_start} "
        f"--end {manifest.operational_end}",
        "Use its compact JSON records as the failure inventory. Do not print raw "
        "logs, the source dataset, or an execution JSONL transcript.",
        "Use these exact regional failure-list links without percent encoding or "
        "locale-specific date formatting:",
        *(f"- {region}: {link}" for region, link in failure_links),
        "After the capture-summary line, use this exact compact section structure:",
        "URLs to validate",
        failure_links[0][1],
        failure_links[1][1],
        "",
        "Message for developer:",
        "  - US Cluster Health: <status and evidence>",
        "  - CA Cluster Health: <status and evidence>",
        "  - ClientA (123), ClientB (456) failed on <same job>: <evidence>",
        "",
        f":bangbang: PROD SUPPORT {operational_date} :bangbang:",
        "US",
        "- Good|Ongoing",
        "  - ClientA (123), ClientB (456) failed on <same job>",
        "CA",
        "- Good|Ongoing",
        "  - ClientC (789) failed on <job1>, <job2>, and <job3>",
        "  - CA cluster is <evidence-derived status>; <symptom1>, <symptom2>, and "
        "<symptom3> appear KEDA status and supporting OMS telemetry are missing",
        "",
        "Follow Ups:",
        "",
        "- Would you like to:",
        "  - [Resend validate_event_bus events for <client>]"
        "(<resource-discovery reviewed application link>) for <date or date range>",
        "  - Follow up with pd-rix about <count> validate_event_bus events for "
        "<client> on <date>.",
        "  - Do you approve re-running the following jobs:",
        "    - <client or grouped clients>: <job>; also move to "
        f"[KPO sizing agent](agent://kpo-sizer/definition) for {operational_date} "
        "when attempts exceed five",
        "Do not use Markdown headings such as '## Developer message' or "
        "'## Data Internal message'. Do not insert blank lines between bullets or "
        "periods anywhere in Data Internal.",
        "Resolve every client UUID found in a DAG or task identifier through the "
        "recorded Resource Discovery input before triage or reporting. Use the "
        "resolved name and first three UUID characters in parentheses. When no "
        "unique reviewed name exists, use 'Unresolved client (<prefix>)'; never "
        "emit a bare prefix.",
        "Never place a CA finding in the US section or a US finding in the CA "
        "section. Do not describe one regional cluster as both healthy and unhealthy "
        "from the same evidence. Treat either defect as a failed final-report audit.",
        "In both audience messages, minimize repetition. Group clients that failed "
        "on the same job into one line. When one client has multiple failures, group "
        "its jobs into one client line. Preserve each failure's evidence in Developer.",
        "For every failed DAG, also provide a DAG grid link using this exact shape:",
        "<airflow-base-url>/dags/<dag-id>/grid?status=failed"
        f"&execution_start={manifest.operational_start}"
        f"&execution_end={manifest.operational_end}",
        "Use read-only automation and fetch the exact Airflow task-attempt log for "
        "every discovered failure. A non-empty discovery log is only an excerpt; "
        "do not stop until terminal evidence, explicit truncation, or an unavailable "
        "log result is established.",
        "After establishing the report heading and window, immediately start three "
        "independent workstreams concurrently: US failures, CA failures, and "
        "US/CA cluster health. Do not serialize these workstreams.",
        "Enumerate every returned failure in both regions with one compact record: "
        "region, DAG ID, run ID, task ID, attempt, exact-log status, source, and at "
        "most three evidence lines. Never emit a full log body.",
        "Required operational workflow:",
        "1. Print a capture-summary line derived from discovered records. When one "
        "region has every failure and the other has none, use: Local capture "
        "contains <N> failures, all from <region>; no <region> failures were recorded.",
        "2. If the latest task log is unavailable or non-diagnostic, page backward "
        "through prior runs of the same DAG and task and cite the first terminal "
        "evidence. Never change task identity.",
        "3. Provide the exact US and CA regional failure links above plus a filtered "
        "DAG grid link for every failed DAG.",
        "4. For each Spark workload, start exact Airflow-log and OMS queries "
        "concurrently. If Airflow proves AirflowTaskTimeout, cancel pending OMS "
        "work and classify the timeout without waiting.",
        "5. Check KEDA ScaledObjects and pod health in both regions. Include explicit "
        "US Cluster Health and CA Cluster Health lines as the first Developer "
        "message bullets, or identify the exact missing evidence. In Data Internal, "
        "describe an unhealthy cluster with one status sentence followed by its "
        "observed symptoms without periods. Treat access-denied results and "
        "capture timestamps as "
        "evidence, never as proof of historical health.",
        "6. Resolve every client UUID found in a DAG or task identifier through the "
        "recorded resource-discovery input before triage. Application selection is "
        "hard-gated on an explicit "
        "reviewed production mapping. Use that mapping to emit a clickable resend "
        "events link for every resend client. If none exists, report an evidence gap "
        "and do not substitute a log directive, client subdomain, Airflow region, or "
        "guessed application.",
        "7. When a resend exceeds 100 unique events, call it out in both the "
        "developer and Data Internal messages.",
        "8. Investigate all failures, but by default omit D2P, MI3, subscriber, "
        "maintenance, backfill, and credit migration matrix (CMM) groups from Data "
        "Internal and rerun follow-ups. "
        "The MCP data_internal_omissions parameter replaces these defaults; an empty "
        "list includes every investigated job.",
        "9. The developer message must account for every discovered failure, "
        "including jobs omitted from Data Internal. Group the same job across "
        "clients and multiple jobs for one client. State only an "
        "evidence-backed root cause; otherwise state the precise evidence gap. Do not "
        "infer event order or causality from unrelated timestamps or errors. Use "
        "client names or short aliases in audience messages; keep raw UUIDs, Spark "
        "IDs, and record references out of audience-facing prose.",
        "10. Follow Ups must contain actions only. A "
        "validate_event_bus_opportunities failure already implies missing snapshots; "
        "keep its Data Internal wording concise. In Follow Ups, include "
        "the exact resend date or range and a reviewed Resource Discovery application "
        "link. If routing "
        "is unresolved, ask to resolve the production link first and do not offer an "
        "unlinked resend. For more than 100 events, add a pd-rix follow-up. Group "
        "identical rerun jobs and ask for approval with the operational date, "
        "excluding every configured omission. When a grouped job exceeds five "
        "attempts, also link the KPO "
        "sizing agent interface at agent://kpo-sizer/definition without invoking it. "
        "Do not repeat diagnoses, evidence-gathering tasks, schema upgrades, or "
        "status summaries in Follow Ups.",
        "11. Audit regional consistency and contradictions. Every finding must appear "
        "under its source region, every cluster status must agree with its cited "
        "evidence, and no client/job pair may be repeated across multiple Data "
        "Internal bullets. Prefer the explicit words timeout, OOM, or distinctness "
        "validation errors when those causes are proven.",
        "Before returning, audit the final report against all eleven workflow items. "
        "Do not claim a check was performed without trace evidence.",
        "Derive dates, paths, clients, and counts from the supplied manifest and "
        "evidence. Do not hard-code this case in worker prompts. Do not inspect Git "
        "history or repository documentation. If a utility is unavailable, use the "
        "Python standard library once; do not retry the same failed command.",
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
