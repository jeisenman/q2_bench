"""Build region-bound Airflow error handoffs for reporting."""

from __future__ import annotations


def errors_by_region(
    groups: list[dict[str, object]],
) -> dict[str, list[str]]:
    """Return explicit regional handoff lines that cannot cross regions."""
    regional: dict[str, list[str]] = {}
    for group in groups:
        region = str(group["region"])
        regional.setdefault(region, []).append(
            f"{group['client']} failed on {group['job']}: {group['root_cause']}"
        )
    return {
        region: [f"For {region} Cluster the following errors exist:", *errors]
        for region, errors in sorted(regional.items())
    }
