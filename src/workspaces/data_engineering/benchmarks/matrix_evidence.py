"""Build the deterministic evidence command shared by prompts and preflight."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Protocol

COMPACT_BRIEF_MODULE = (
    "workspaces.data_engineering.benchmarks.production_support.compact_brief"
)
COMPACT_BRIEF_FILE = "compact_brief.py"


class EvidenceManifest(Protocol):
    """Manifest fields required to construct a recorded-evidence command."""

    @property
    def dataset(self) -> Path:
        """Return the primary recorded dataset."""
        ...

    @property
    def candidate_inputs(self) -> tuple[Path, ...]:
        """Return additional recorded candidate inputs."""
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
    def applicability(self) -> tuple[tuple[str, bool], ...]:
        """Return criterion applicability declared by the case."""
        ...


def compact_brief_arguments(
    manifest: EvidenceManifest,
    output: str,
) -> tuple[str, ...] | None:
    """Return parser arguments when the selected case uses compact evidence."""
    inputs_by_name = {path.name: str(path) for path in manifest.candidate_inputs}
    if COMPACT_BRIEF_FILE not in inputs_by_name:
        return None
    applicability = dict(manifest.applicability)
    arguments = [
        "-m",
        COMPACT_BRIEF_MODULE,
        "--dataset",
        str(manifest.dataset),
        "--start",
        manifest.operational_start,
        "--end",
        manifest.operational_end,
    ]
    optional_inputs = (
        ("cluster_health_snapshot.json", "--cluster-health", None),
        ("resource_discovery_snapshot.json", "--resource-discovery", None),
        ("multi_run_log_fallback.json", "--prior-run-logs", None),
        ("relationship_signals_prior_day.json", "--prior-context", None),
    )
    for name, flag, criterion in optional_inputs:
        if name in inputs_by_name and (
            criterion is None or applicability.get(criterion, True)
        ):
            arguments.extend((flag, inputs_by_name[name]))
    arguments.extend(("--output", output))
    return tuple(arguments)


def compact_brief_shell_command(manifest: EvidenceManifest) -> str | None:
    """Return the exact candidate-facing compact evidence command."""
    arguments = compact_brief_arguments(
        manifest,
        "/tmp/prod-support-compact-evidence.json",
    )
    if arguments is None:
        return None
    return f"PYTHONPATH=src python3 {shlex.join(arguments)}"
