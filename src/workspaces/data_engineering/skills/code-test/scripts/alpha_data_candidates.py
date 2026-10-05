"""Statically shortlist Alpha datasets and Contx resources for changed jobs."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

DEFAULT_CLIENT_ID: Final = "99b9412b-70fd-4221-8431-d1b3934889ec"
SOURCE_ROOTS: Final = ("dags", "de-jobs", "ds-jobs", "ra-jobs", "dag-utils")
DATASTORE_MARKERS: Final = ("adls", "storage", "datalake")
SAFE_DATASTORE_FIELDS: Final = (
    "name",
    "kind",
    "groups",
    "host_name",
    "domain",
    "path",
    "region",
    "resource_group_name",
    "subscription_id",
)


class AnalysisError(RuntimeError):
    """Raised when static Alpha-data analysis cannot produce safe evidence."""


@dataclass(slots=True)
class StaticEvidence:
    """Collected source literals grouped by their likely operational meaning."""

    job_references: set[str] = field(default_factory=set)
    datasets: set[str] = field(default_factory=set)
    versions: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)
    formats: set[str] = field(default_factory=set)
    resources: set[str] = field(default_factory=set)
    field_occurrences: dict[str, set[str]] = field(default_factory=dict)

    def merge(self, other: StaticEvidence) -> None:
        """Merge another evidence collection into this value."""
        self.job_references.update(other.job_references)
        self.datasets.update(other.datasets)
        self.versions.update(other.versions)
        self.paths.update(other.paths)
        self.formats.update(other.formats)
        self.resources.update(other.resources)
        for name, paths in other.field_occurrences.items():
            self.field_occurrences.setdefault(name, set()).update(paths)

    def to_dict(self) -> dict[str, object]:
        """Return deterministically ordered JSON-safe evidence."""
        return {
            "job_references": sorted(self.job_references),
            "datasets": sorted(self.datasets),
            "versions": sorted(self.versions),
            "paths": sorted(self.paths),
            "formats": sorted(self.formats),
            "resources": sorted(self.resources),
            "field_occurrences": {
                name: sorted(paths)
                for name, paths in sorted(self.field_occurrences.items())
            },
        }


def changed_python_files(repository: Path, base_ref: str) -> tuple[Path, ...]:
    """Return changed, tracked Python files beneath supported source roots."""
    if not repository.is_dir():
        raise AnalysisError(f"DI Pipelines repository does not exist: {repository}")
    command = (
        "git",
        "-C",
        str(repository),
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        f"{base_ref}...HEAD",
    )
    result = subprocess.run(command, capture_output=True, check=False, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown Git error"
        raise AnalysisError(f"Cannot diff against {base_ref}: {detail}")
    paths = []
    for value in result.stdout.splitlines():
        relative = Path(value)
        if relative.suffix == ".py" and relative.parts[:1] in {
            (root,) for root in SOURCE_ROOTS
        }:
            paths.append(repository / relative)
    return tuple(sorted(paths))


def resolve_base_ref(repository: Path, requested: str) -> str:
    """Resolve an explicit ref or the repository's first conventional base ref."""
    candidates = (
        (requested,)
        if requested != "auto"
        else ("origin/main", "origin/master", "main", "master")
    )
    for candidate in candidates:
        result = subprocess.run(
            ("git", "-C", str(repository), "rev-parse", "--verify", candidate),
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            return candidate
    choices = ", ".join(candidates)
    raise AnalysisError(f"Cannot resolve a base ref from: {choices}")


def extract_static_evidence(
    paths: Iterable[Path],
    repository: Path,
    requested_fields: Sequence[str],
) -> StaticEvidence:
    """Extract likely job, dataset, version, path, format, and field literals."""
    evidence = StaticEvidence(
        field_occurrences={field_name: set() for field_name in requested_fields}
    )
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise AnalysisError(f"Cannot parse {path}: {exc}") from exc
        relative = str(path.relative_to(repository))
        for field_name in requested_fields:
            if field_name in source:
                evidence.field_occurrences[field_name].add(relative)
        visitor = LiteralVisitor()
        visitor.visit(tree)
        evidence.job_references.update(visitor.job_references)
        evidence.datasets.update(visitor.datasets)
        evidence.versions.update(visitor.versions)
        evidence.paths.update(visitor.paths)
        evidence.formats.update(visitor.formats)
        evidence.resources.update(visitor.resources)
    return evidence


class LiteralVisitor(ast.NodeVisitor):
    """Collect string literals attached to operationally meaningful names."""

    def __init__(self) -> None:
        """Initialize empty evidence collections."""
        self.job_references: set[str] = set()
        self.datasets: set[str] = set()
        self.versions: set[str] = set()
        self.paths: set[str] = set()
        self.formats: set[str] = set()
        self.resources: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        """Collect literals from ordinary assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._collect(target.id, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Collect literals from annotated assignments."""
        if isinstance(node.target, ast.Name) and node.value is not None:
            self._collect(node.target.id, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Collect literals from named call arguments."""
        for keyword in node.keywords:
            if keyword.arg:
                self._collect(keyword.arg, keyword.value)
        self.generic_visit(node)

    def _collect(self, name: str, node: ast.AST) -> None:
        normalized = name.lower().replace("-", "_")
        values = _string_values(node)
        if "job_reference" in normalized or normalized == "job_name":
            self.job_references.update(values)
        elif "resource" in normalized or "datastore" in normalized:
            self.resources.update(values)
        elif "version" in normalized:
            self.versions.update(values)
        elif "dataset" in normalized:
            self.datasets.update(values)
        elif "format" in normalized:
            self.formats.update(values)
        elif any(marker in normalized for marker in ("path", "file", "folder")):
            self.paths.update(values)


def related_job_files(
    repository: Path,
    job_references: Iterable[str],
    changed_paths: Iterable[Path],
) -> tuple[Path, ...]:
    """Find Python files that define or use extracted job references."""
    changed = set(changed_paths)
    references = tuple(sorted(set(job_references)))
    if not references:
        return ()
    matches = []
    for root_name in SOURCE_ROOTS:
        root = repository / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path in changed:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise AnalysisError(f"Cannot read {path}: {exc}") from exc
            if any(reference in source for reference in references):
                matches.append(path)
    return tuple(sorted(matches))


def shortlist_contx_resources(
    metadata_root: Path,
    client_id: str,
    resource_kinds: Iterable[str] = (),
) -> tuple[dict[str, object], ...]:
    """Return safe storage resources relevant to one client partition."""
    partitions_path = metadata_root / "application_partitions.json"
    datastores_path = metadata_root / "datastores.json"
    partitions = _load_json(partitions_path).get("ApplicationPartitionsMetadata", [])
    datastore_document = _load_json(datastores_path)
    datastore_metadata = datastore_document.get("DatastoresMetadata", {})
    datastores = (
        datastore_metadata.get("instances", [])
        if isinstance(datastore_metadata, dict)
        else []
    )
    if not isinstance(partitions, list) or not isinstance(datastores, list):
        raise AnalysisError(f"Unexpected Contx metadata shape under {metadata_root}")

    selected = [
        item
        for item in partitions
        if isinstance(item, dict)
        and item.get("is_active") is True
        and item.get("application") == "precisionlender"
        and item.get("name") == client_id
    ]
    if not selected:
        raise AnalysisError(
            f"Active PrecisionLender partition not found for {client_id}"
        )
    groups = {
        str(selected[0].get(key))
        for key in ("client_group", "shared_group")
        if selected[0].get(key)
    }
    requested_kinds = {value.lower() for value in resource_kinds}
    results = []
    for item in datastores:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).lower()
        item_groups = {str(group) for group in item.get("groups", [])}
        if groups.isdisjoint(item_groups) or not any(
            marker in kind for marker in DATASTORE_MARKERS
        ):
            continue
        if requested_kinds and kind not in requested_kinds:
            continue
        results.append(
            {
                key: item[key]
                for key in SAFE_DATASTORE_FIELDS
                if item.get(key) is not None
            }
        )
    return tuple(sorted(results, key=lambda item: (str(item.get("kind")), str(item))))


def analyze(
    repository: Path,
    metadata_root: Path,
    base_ref: str,
    client_id: str,
    fields: Sequence[str],
    environment: str = "alpha",
) -> dict[str, object]:
    """Build the static handoff used before MCP and Azure data inspection."""
    if not fields:
        raise AnalysisError("At least one --field is required")
    resolved_base = resolve_base_ref(repository, base_ref)
    changed = changed_python_files(repository, resolved_base)
    candidate_files = tuple(
        path
        for path in changed
        if any(field_name in path.read_text(encoding="utf-8") for field_name in fields)
    )
    if not candidate_files:
        requested = ", ".join(fields)
        raise AnalysisError(
            f"Changed files do not contain requested fields: {requested}"
        )
    changed_evidence = extract_static_evidence(candidate_files, repository, fields)
    related = related_job_files(repository, changed_evidence.job_references, changed)
    all_evidence = StaticEvidence(
        field_occurrences={field_name: set() for field_name in fields}
    )
    all_evidence.merge(changed_evidence)
    all_evidence.merge(extract_static_evidence(related, repository, fields))
    resource_kinds = all_evidence.resources
    if not resource_kinds and "Primary" in all_evidence.paths:
        resource_kinds = {"OperationalADLS"}
    return {
        "client_id": client_id,
        "environment": environment,
        "base_ref": resolved_base,
        "changed_files": [str(path.relative_to(repository)) for path in changed],
        "candidate_files": [
            str(path.relative_to(repository)) for path in candidate_files
        ],
        "related_job_files": [str(path.relative_to(repository)) for path in related],
        "static_evidence": all_evidence.to_dict(),
        "contx_resources": list(
            shortlist_contx_resources(
                metadata_root,
                client_id,
                resource_kinds,
            )
        ),
        "next_step": (
            "Use the shortlisted resources and declared dataset paths with "
            "lookup_azure_resources, then inspect the smallest matching partition."
        ),
    }


def _string_values(node: ast.AST) -> set[str]:
    values = {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and child.value.strip()
    }
    return {value.strip() for value in values}


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise AnalysisError(f"Required Contx metadata does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read Contx metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnalysisError(f"Contx metadata must be an object: {path}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("../di-pipelines"))
    parser.add_argument(
        "--contx-alpha",
        type=Path,
        default=Path("../di-scheduling/Deployment/ContxMetadata/alpha"),
    )
    parser.add_argument("--base-ref", default="auto")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--environment", choices=("alpha", "staging"), default="alpha")
    parser.add_argument("--field", action="append", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the static Alpha-data candidate analysis and print JSON."""
    args = _parser().parse_args(argv)
    try:
        result = analyze(
            args.repository.resolve(),
            args.contx_alpha.resolve(),
            args.base_ref,
            args.client_id,
            tuple(args.field),
            args.environment,
        )
    except AnalysisError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
