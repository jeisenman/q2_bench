#!/usr/bin/env python3
"""Identify Derived RA rerun targets from high_quality distinctness results."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from oms import (
    REGIONS,
    collect_message_text,
    default_timespan,
    escape_kusto,
    query,
)

KNOWN_JOBS = {
    "coreaccountdetails": "ra_group.get_core_account_details",
    "coreaccountfinancialstatements": "ra_group.get_core_account_financial_statements",
    "coredepositaccounts": "ra_group.get_core_deposit_accounts",
    "depositproducts": "ra_group.get_core_deposit_accounts",
    "depositfinancialstatementsbreakdown": (
        "ra_group.get_deposit_financial_statement_breakdown"
    ),
    "coreloanaccounts": "ra_group.get_core_loan_accounts",
    "commercialloanaccounts": "ra_group.get_core_loan_accounts",
    "commercialloanproducts": "ra_group.get_core_loan_accounts",
    "consumerloanaccounts": "ra_group.get_core_loan_accounts",
    "consumerloanproducts": "ra_group.get_core_loan_accounts",
    "coreaccountsupplementaldata": "ra_group.get_core_loan_accounts",
    "coreaccountsupplimentaldata": "ra_group.get_core_loan_accounts",
    "mastercommitmentloanaccounts": "ra_group.get_core_loan_accounts",
    "mastercommitmentloanproducts": "ra_group.get_core_loan_accounts",
    "loanfinancialstatementsbreakdown": (
        "ra_group.get_loan_financial_statement_breakdown"
    ),
    "coreotheraccounts": "ra_group.get_core_other_accounts",
    "otherproducts": "ra_group.get_core_other_accounts",
    "otherfinancialstatementsbreakdown": "ra_group.get_core_other_accounts",
    "coretreasuryaccounts": "ra_group.get_core_treasury_accounts",
    "treasuryaccounts": "ra_group.get_core_treasury_accounts",
    "treasuryproducts": "ra_group.get_core_treasury_accounts",
    "treasurycategories": "ra_group.get_core_treasury_accounts",
    "treasuryfinancialstatementbreakdown": "ra_group.get_core_treasury_accounts",
    "rarelationships": "ra_group.get_relationships",
    "relationships": "ra_group.get_relationships",
    "relationshipfinancialstatements": "ra_group.get_relationships",
    "relationshipaggregatedbalances": "ra_group.get_relationships",
}
BEGIN = re.compile(r"Validate distinctness - begin:\s*(.+?)\s*$", re.IGNORECASE)
FAILURE = re.compile(
    r"Distinctness validation failed for\s+(.+?)\s+on\s+", re.IGNORECASE
)
COUNTS = re.compile(
    r"Validate distinctness - counts:\s*(.+?)\s*-\s*total:\s*(\d+)\s*;\s*unique:\s*(\d+)",
    re.IGNORECASE,
)
TIMEOUT = re.compile(r"\*\*TimeoutError:", re.IGNORECASE)


def normalise_dataset_form(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]", "", value)
    return re.sub(r"(?:derived|data)$", "", value, flags=re.IGNORECASE).lower()


def get_job_name(dataset_form: str) -> str:
    """Map a logged DatasetForm to the high_quality task-group factory name."""
    normalised = normalise_dataset_form(dataset_form)
    if job := KNOWN_JOBS.get(normalised):
        return job
    snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", dataset_form).lower()
    snake_case = re.sub(r"[^a-z0-9]+", "_", snake_case).strip("_")
    snake_case = re.sub(r"_(derived|data)$", "", snake_case)
    return f"ra_group.get_{snake_case}"


def parse_distinctness_results(
    text: str,
) -> tuple[dict[str, tuple[int, int]], set[str]]:
    """Return all count results and DatasetForms with explicit or count mismatches."""
    results: dict[str, tuple[int, int]] = {}
    failures: set[str] = set()
    for line in text.splitlines():
        if match := FAILURE.search(line):
            dataset = match.group(1).strip()
            if "{" not in dataset and "}" not in dataset:
                failures.add(dataset)
            continue
        if match := COUNTS.search(line):
            dataset, total, unique = match.groups()
            results[dataset.strip()] = (int(total), int(unique))
            if total != unique:
                failures.add(dataset.strip())
    return results, failures


def kusto_query(client_id: str, task_id: str, run_id: str) -> str:
    client_id = escape_kusto(client_id)
    task_id = escape_kusto(task_id)
    run_id = escape_kusto(run_id)
    return f"""DI_Scheduling_CL
| where client_id_g == '{client_id}'
| where task_id_s == '{task_id}'
| where run_id_s == '{run_id}'
| where Message has 'Validate distinctness' or Message has 'Distinctness validation failed'
| project TimeGenerated, Message
| order by TimeGenerated asc"""


def read_log_file(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text()


def valid_high_quality_task(task_id: str) -> bool:
    return task_id.rsplit(".", 1)[-1].startswith("high_quality_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True, choices=REGIONS)
    parser.add_argument("--client-id", required=True)
    parser.add_argument(
        "--task-id", required=True, help="Failed Airflow high_quality task ID."
    )
    parser.add_argument(
        "--run-id", help="Failed Airflow DAG run ID; required without --log-file."
    )
    parser.add_argument(
        "--start-utc", help="Start of the Log Analytics query window in UTC."
    )
    parser.add_argument(
        "--end-utc", help="End of the Log Analytics query window in UTC."
    )
    parser.add_argument(
        "--log-file", help="Parse captured task logs instead; use - for stdin."
    )
    args = parser.parse_args()

    if not valid_high_quality_task(args.task_id):
        parser.error("--task-id must name a high_quality_* Derived RA task")
    if args.log_file:
        log_text = read_log_file(args.log_file)
    else:
        if not args.run_id:
            parser.error("--run-id is required unless --log-file is provided")
        start, end = default_timespan(args.start_utc, args.end_utc)
        try:
            log_text = collect_message_text(
                query(
                    args.region,
                    kusto_query(args.client_id, args.task_id, args.run_id),
                    start,
                    end,
                )
            )
        except RuntimeError as error:
            print(f"Unable to get high_quality task logs: {error}", file=sys.stderr)
            return 1

    results, failures = parse_distinctness_results(log_text)
    if not failures:
        if TIMEOUT.search(log_text):
            print(
                "TimeoutError detected; classify this failure as a timeout. Do not rerun from this analysis."
            )
            return 0
        print("No Validate distinctness errors found; do not rerun from this analysis.")
        return 0
    datasets = sorted(set(results) | failures)
    jobs = sorted({get_job_name(dataset) for dataset in failures})
    print(f"Validate distinctness checks on {args.client_id}:")
    for dataset in sorted(results):
        total, unique = results[dataset]
        status = "mismatch" if total != unique else "pass"
        print(f"- {dataset}: total {total}; unique {unique}; {status}")
    for dataset in sorted(failures - set(results)):
        print(f"- {dataset}: explicit distinctness error")
    print(
        f"Validate distinctness error on {args.client_id}; suggest re-running only "
        "the mapped RA jobs with proven mismatches or explicit failures:"
    )
    print(f"l3-main-{args.client_id}")
    for job in jobs:
        print(job)
    print("\nDetected DatasetForms:")
    for dataset in datasets:
        print(f"{dataset} -> {get_job_name(dataset)}")
    print(
        "\nOperator action required: rerun the listed jobs in Airflow, one task at a time. This script made no rerun."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
