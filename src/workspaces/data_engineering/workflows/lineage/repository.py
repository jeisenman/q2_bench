"""Repository manifest construction for deterministic lineage versions."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)
from workspaces.data_engineering.workflows.lineage.graph_models import (
    RepositoryManifest,
    RepositoryRevision,
)

EXTRACTOR_VERSION = "2"
RADAR_EXTRACTOR_VERSION = "3"
MAXIMUM_PERMISSIONS_PROFILE = "maximum-permissions"
RADAR_LINEAGE_REPOSITORY = "precisionlender/radar-lineage"
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


def repository_revision(
    repository: Path,
    *,
    source_ref: str | None = None,
) -> RepositoryRevision:
    """Inspect one checkout without assigning it a graph identity."""
    resolved = repository.resolve()
    commit_sha = _git(resolved, "rev-parse", "HEAD")
    selected_ref = (
        source_ref or _git(resolved, "branch", "--show-current") or commit_sha
    )
    return RepositoryRevision(
        repository=_repository_name(resolved),
        commit_sha=commit_sha,
        source_ref=selected_ref,
    )


def radar_manifest(
    repositories: Mapping[str, Path],
    *,
    generated_at: datetime | None = None,
    source_ref: str | None = None,
) -> RepositoryManifest:
    """Build one deterministic revision from all RADAR source checkouts."""
    revisions = tuple(
        sorted(
            (repository_revision(path) for path in repositories.values()),
            key=lambda item: item.repository,
        )
    )
    revision_key = "\n".join(
        f"{item.repository}:{item.commit_sha}" for item in revisions
    )
    commit_sha = hashlib.sha256(revision_key.encode()).hexdigest()[:40]
    graph_key = ":".join(
        (
            RADAR_LINEAGE_REPOSITORY,
            commit_sha,
            MAXIMUM_PERMISSIONS_PROFILE,
            RADAR_EXTRACTOR_VERSION,
        )
    )
    return RepositoryManifest(
        graph_id=uuid5(NAMESPACE_URL, graph_key),
        repository=RADAR_LINEAGE_REPOSITORY,
        commit_sha=commit_sha,
        source_ref=source_ref or "static-analysis",
        profile=MAXIMUM_PERMISSIONS_PROFILE,
        extractor_version=RADAR_EXTRACTOR_VERSION,
        generated_at=generated_at or datetime.now(UTC),
        source_repositories=revisions,
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
