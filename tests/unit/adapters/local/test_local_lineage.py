from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from adapters.local import (
    LINEAGE_GRAPH_PATH_ENV,
    JsonLineageGraphSource,
    LocalLineageError,
)
from workspaces.data_engineering.workflows.lineage import (
    LineageGraph,
    LineageNode,
    RepositoryManifest,
    dataset_identifier,
)

REPOSITORY = "precisionlender/di-pipelines"
PROFILE = "maximum-permissions"


def graph() -> LineageGraph:
    return LineageGraph(
        RepositoryManifest(
            graph_id=UUID("11111111-1111-1111-1111-111111111111"),
            repository=REPOSITORY,
            commit_sha="a" * 40,
            source_ref="master",
            profile=PROFILE,
            extractor_version="2",
            generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        ),
        (LineageNode(dataset_identifier("Primary", "PL/Chats")),),
        (),
    )


def test_local_lineage_source_reads_matching_graph_and_history(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "lineage.json"
    expected = graph()
    path.write_text(expected.to_json(), encoding="utf-8")
    monkeypatch.setenv(LINEAGE_GRAPH_PATH_ENV, str(path))
    source = JsonLineageGraphSource.from_environment()

    assert source.latest(REPOSITORY, PROFILE) == expected
    assert source.latest("other", PROFILE) is None
    assert source.history(REPOSITORY, PROFILE, 1) == (expected,)
    with pytest.raises(ValueError, match="at least 1"):
        source.history(REPOSITORY, PROFILE, 0)


def test_local_lineage_source_fails_for_missing_or_invalid_artifacts(
    tmp_path,
) -> None:
    missing = JsonLineageGraphSource(tmp_path / "missing.json")
    with pytest.raises(LocalLineageError, match="lineage-sync"):
        missing.latest(REPOSITORY, PROFILE)

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(["not", "a", "graph"]), encoding="utf-8")
    with pytest.raises(LocalLineageError, match="JSON object"):
        JsonLineageGraphSource(invalid).latest(REPOSITORY, PROFILE)
