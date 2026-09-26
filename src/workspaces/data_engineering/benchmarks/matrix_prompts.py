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
            f"?_flt_1_start_date={manifest.operational_start}"
            "&_flt_3_state=failed"
            f"&_flt_2_start_date={manifest.operational_end}#",
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
        "Use these exact regional failure-list links without percent encoding or "
        "locale-specific date formatting:",
        *(f"- {region}: {link}" for region, link in failure_links),
        "After the capture-summary line, use this exact compact section structure:",
        "URLs to validate",
        failure_links[0][1],
        failure_links[1][1],
        "",
        "Message for developer:",
        "  - <one client or one known recurring issue per bullet>",
        "",
        "Message for Data Internal Channel",
        f":bangbang: PROD SUPPORT {operational_date} :bangbang:",
        "US",
        "- Good|Ongoing",
        "  - <one client and its combined findings>",
        "CA",
        "- Good|Ongoing",
        "Do not use Markdown headings such as '## Developer message' or "
        "'## Data Internal message'. Do not insert blank lines between bullets.",
        "In Data Internal, use exactly one client per bullet, combine multiple "
        "findings for that client, and abbreviate a resolved client UUID to its "
        "first three characters in parentheses without an ellipsis.",
        "For every failed DAG, also provide a DAG grid link using this exact shape:",
        "<airflow-base-url>/dags/<dag-id>/grid?status=failed"
        f"&execution_start={manifest.operational_start}"
        f"&execution_end={manifest.operational_end}",
        "Use read-only automation and inspect exact Airflow task logs.",
        "After establishing the report heading and window, immediately start three "
        "independent workstreams concurrently: US failures, CA failures, and "
        "US/CA cluster health. Do not serialize these workstreams.",
        "Enumerate every returned Airflow failure in both regions. Preserve each "
        "failure's region, DAG ID, run ID, task ID, exact-log lookup, and evidence "
        "outcome in the JSONL execution trace. Do not replace the complete inventory "
        "with grouped counts.",
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
        "US Cluster Health and CA Cluster Health lines, or identify the exact "
        "missing evidence. Treat access-denied results and capture timestamps as "
        "evidence, never as proof of historical health.",
        "6. Resolve every resend client through the recorded resource-discovery "
        "input. Application selection is hard-gated on an explicit reviewed "
        "production mapping. If none exists, report routing unresolved and do not "
        "substitute a log directive, client subdomain, or guessed application.",
        "7. When a resend exceeds 100 unique events, call it out in both the "
        "developer and Data Internal messages.",
        "8. Investigate all failures, but omit configured maintenance and subscriber "
        "jobs from the Data Internal message.",
        "9. The developer message must contain one explicit entry for every discovered "
        "failure, including jobs omitted from Data Internal. State only an "
        "evidence-backed root cause; otherwise state the precise evidence gap. Do not "
        "infer event order or causality from unrelated timestamps or errors. Use "
        "client names or short aliases in audience messages; keep raw UUIDs, Spark "
        "IDs, and record references out of audience-facing prose.",
        "Before returning, audit the final report against all nine workflow items. "
        "Do not claim a check was performed without trace evidence.",
        "Do not mutate production systems. Return the final report only.",
    ]
