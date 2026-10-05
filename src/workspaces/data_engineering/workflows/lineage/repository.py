"""Repository manifest construction for deterministic lineage versions."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)
from workspaces.data_engineering.workflows.lineage.graph_models import (
    RepositoryManifest,
)

EXTRACTOR_VERSION = "2"
MAXIMUM_PERMISSIONS_PROFILE = "maximum-permissions"
REMOTE_REPOSITORY_PARTS = 2


def repository_manifest(
    repository: Path,
    *,
    generated_at: datetime | None = None,
    source_ref: str | None = None,
) -> RepositoryManifest:
    """Build a stable manifest from the checked-out repository revision."""
    resolved = repository.resolve()
    commit_sha = _git(resolved, "rev-parse", "HEAD")
    repository_name = _repository_name(resolved)
    selected_ref = (
        source_ref or _git(resolved, "branch", "--show-current") or commit_sha
    )
    graph_key = ":".join(
        (
            repository_name,
            commit_sha,
            MAXIMUM_PERMISSIONS_PROFILE,
            EXTRACTOR_VERSION,
        )
    )
    return RepositoryManifest(
        graph_id=uuid5(NAMESPACE_URL, graph_key),
        repository=repository_name,
        commit_sha=commit_sha,
        source_ref=selected_ref,
        profile=MAXIMUM_PERMISSIONS_PROFILE,
        extractor_version=EXTRACTOR_VERSION,
        generated_at=generated_at or datetime.now(UTC),
    )


def _repository_name(repository: Path) -> str:
    remote = _git(repository, "remote", "get-url", "origin", required=False)
    if not remote:
        return repository.name
    trimmed = remote.removesuffix(".git").rstrip("/")
    if ":" in trimmed and "/" not in trimmed.split(":", maxsplit=1)[0]:
        trimmed = trimmed.rsplit(":", maxsplit=1)[-1]
    parts = [part for part in trimmed.split("/") if part]
    return (
        "/".join(parts[-REMOTE_REPOSITORY_PARTS:])
        if len(parts) >= REMOTE_REPOSITORY_PARTS
        else repository.name
    )


def _git(
    repository: Path,
    *arguments: str,
    required: bool = True,
) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=required,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError) and error.stderr
            else str(error)
        )
        raise LineageValidationError.git_inspection(str(repository), detail) from error
    return result.stdout.strip()
