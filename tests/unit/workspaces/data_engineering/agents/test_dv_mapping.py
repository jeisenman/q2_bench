"""Tests for evidence-qualified Derived RA target mapping."""

from workspaces.data_engineering.agents.production_support import (
    map_distinctness_targets,
)


def test_maps_only_mismatched_dataset_to_exact_upstream_task() -> None:
    result = map_distinctness_targets(
        "Validate distinctness - counts: CoreAccounts - total: 12; unique: 12\n"
        "Validate distinctness - counts: DepositFinancialStatementsBreakdown "
        "- total: 15; unique: 9\n"
        "Distinctness validation failed for "
        "DepositFinancialStatementsBreakdown on account_id"
    )

    assert [check.status for check in result.checks] == ["pass", "mismatch"]
    assert result.failed_datasets == ("DepositFinancialStatementsBreakdown",)
    assert result.rerun_targets == (
        "ra_group.get_deposit_financial_statement_breakdown",
    )


def test_maps_explicit_failure_without_counts() -> None:
    result = map_distinctness_targets(
        "Distinctness validation failed for LoanFinancialStatementsBreakdown"
    )

    assert result.failed_datasets == ("LoanFinancialStatementsBreakdown",)
    assert result.rerun_targets == ("ra_group.get_loan_financial_statement_breakdown",)


def test_unknown_dataset_uses_deterministic_ra_group_fallback() -> None:
    result = map_distinctness_targets(
        "Validate distinctness - counts: NewAccountFacts - total: 3; unique: 2"
    )

    assert result.rerun_targets == ("ra_group.get_new_account_facts",)
