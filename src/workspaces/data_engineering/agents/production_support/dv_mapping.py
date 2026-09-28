"""Map proven distinctness failures to exact upstream RA task IDs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from workspaces.data_engineering.agents.production_support.models import (
    DistinctnessCheck,
)

COUNT_PATTERN = re.compile(
    r"Validate distinctness - counts:\s*"
    r"(?P<dataset>.+?)\s*-\s*"
    r"total:\s*(?P<total>\d+)\s*;\s*unique:\s*(?P<unique>\d+)",
    re.IGNORECASE,
)
FAILURE_PATTERN = re.compile(
    r"Distinctness validation failed for\s+(?P<dataset>.+?)(?:\s+on\s+|$)",
    re.IGNORECASE,
)
KNOWN_UPSTREAM_TASKS = {
    "coreaccountdetails": "ra_group.get_core_account_details",
    "coreaccountfinancialstatements": (
        "ra_group.get_core_account_financial_statements"
    ),
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


@dataclass(frozen=True, slots=True)
class DvMappingResult:
    """Parsed DV checks and exact upstream rerun targets."""

    checks: tuple[DistinctnessCheck, ...]
    failed_datasets: tuple[str, ...]
    rerun_targets: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def has_failure(self) -> bool:
        """Return whether exact evidence proves a distinctness failure."""
        return bool(self.failed_datasets)


def map_distinctness_targets(log: str) -> DvMappingResult:
    """Parse DV evidence and map only failed DatasetForms upstream."""
    normalized = log.replace("\\n", "\n")
    checks_by_dataset: dict[str, DistinctnessCheck] = {}
    evidence_by_dataset: dict[str, str] = {}
    explicit_failures: list[str] = []
    explicit_evidence: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if match := COUNT_PATTERN.search(line):
            dataset = match["dataset"].strip()
            checks_by_dataset[dataset] = DistinctnessCheck(
                dataset=dataset,
                total=int(match["total"]),
                unique=int(match["unique"]),
            )
            evidence_by_dataset[dataset] = line
        if match := FAILURE_PATTERN.search(line):
            dataset = match["dataset"].strip()
            if "{" not in dataset and dataset not in explicit_failures:
                explicit_failures.append(dataset)
                explicit_evidence.append(line)
    mismatches = tuple(
        check.dataset
        for check in checks_by_dataset.values()
        if check.status == "mismatch"
    )
    failed_datasets = tuple(dict.fromkeys((*mismatches, *explicit_failures)))
    rerun_targets = tuple(
        dict.fromkeys(_upstream_task(dataset) for dataset in failed_datasets)
    )
    mismatch_evidence = tuple(
        evidence_by_dataset[dataset]
        for dataset in mismatches
        if dataset in evidence_by_dataset
    )
    passing_evidence = tuple(
        evidence_by_dataset[check.dataset]
        for check in checks_by_dataset.values()
        if check.status == "pass"
    )
    return DvMappingResult(
        checks=tuple(checks_by_dataset.values()),
        failed_datasets=failed_datasets,
        rerun_targets=rerun_targets,
        evidence=tuple(
            dict.fromkeys((*mismatch_evidence, *explicit_evidence, *passing_evidence))
        ),
    )


def _upstream_task(dataset: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", dataset).lower()
    if target := KNOWN_UPSTREAM_TASKS.get(normalized):
        return target
    snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", dataset).lower()
    snake_case = re.sub(r"[^a-z0-9]+", "_", snake_case).strip("_")
    return f"ra_group.get_{snake_case}"
