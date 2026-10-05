"""Specific errors raised by lineage extraction and persistence."""

from __future__ import annotations


class LineageValidationError(ValueError):
    """Raised when a lineage contract or source boundary is invalid."""

    @classmethod
    def empty_identifier(cls, label: str) -> LineageValidationError:
        """Return an error for an empty canonical identifier component."""
        return cls(f"canonical {label} must not be empty")

    @classmethod
    def invalid_segment(cls, value: str) -> LineageValidationError:
        """Return an error for an identifier without usable characters."""
        return cls(f"identifier segment {value!r} has no usable characters")

    @classmethod
    def empty_dataset_path(cls) -> LineageValidationError:
        """Return an error for an empty logical dataset path."""
        return cls("dataset path must contain at least one segment")

    @classmethod
    def empty_edge_endpoint(cls) -> LineageValidationError:
        """Return an error for an incomplete graph edge."""
        return cls("lineage edge endpoints must not be empty")

    @classmethod
    def invalid_commit_sha(cls) -> LineageValidationError:
        """Return an error for a non-SHA-1 repository revision."""
        return cls("repository commit SHA must contain 40 characters")

    @classmethod
    def naive_generated_at(cls) -> LineageValidationError:
        """Return an error for a manifest without timezone information."""
        return cls("manifest generated_at must be timezone-aware")

    @classmethod
    def duplicate_nodes(cls) -> LineageValidationError:
        """Return an error for duplicate canonical graph nodes."""
        return cls("lineage graph contains duplicate node identifiers")

    @classmethod
    def missing_nodes(cls, missing: list[str]) -> LineageValidationError:
        """Return an error for graph edges with unresolved endpoints."""
        return cls(f"lineage graph edges reference missing nodes: {missing}")

    @classmethod
    def missing_source(cls, path: str) -> LineageValidationError:
        """Return an error for a configured source file that is absent."""
        return cls(f"lineage source file does not exist: {path}")

    @classmethod
    def git_inspection(cls, repository: str, detail: str) -> LineageValidationError:
        """Return an error when repository revision metadata cannot be read."""
        return cls(f"unable to inspect Git repository {repository}: {detail}")
