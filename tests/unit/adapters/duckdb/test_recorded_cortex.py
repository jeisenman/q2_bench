import asyncio
from pathlib import Path

import pytest

from adapters.duckdb.cortex import (
    CortexRecordingError,
    RecordedCortex,
    recording_key,
    write_recording,
)
from domain.environments import Environment
from ports.cortex import CortexRequest, CortexUnavailableError

REQUEST = CortexRequest(model="llama3.1-8b", prompt="Summarize the failure.")


@pytest.fixture
def recordings(tmp_path: Path) -> Path:
    write_recording(tmp_path, REQUEST, "A disk filled up.", 5)
    return tmp_path


def test_recorded_response_replays_deterministically(recordings: Path) -> None:
    cortex = RecordedCortex.from_directory(recordings)

    first = asyncio.run(cortex.complete(REQUEST))
    second = asyncio.run(cortex.complete(REQUEST))

    assert first.text == second.text == "A disk filled up."
    assert first.environment is Environment.SANDBOX


def test_replayed_responses_are_marked_as_recorded(recordings: Path) -> None:
    response = asyncio.run(RecordedCortex.from_directory(recordings).complete(REQUEST))

    assert response.recorded is True


def test_an_unrecorded_request_fails_instead_of_inventing_an_answer(
    recordings: Path,
) -> None:
    cortex = RecordedCortex.from_directory(recordings)
    unseen = CortexRequest(model="llama3.1-8b", prompt="A prompt never captured.")

    with pytest.raises(CortexRecordingError, match="no recorded Cortex response"):
        asyncio.run(cortex.complete(unseen))


def test_a_changed_prompt_is_a_different_recording() -> None:
    other = CortexRequest(model=REQUEST.model, prompt="Different prompt.")

    assert recording_key(other) != recording_key(REQUEST)


def test_token_counts_replay_and_fail_loudly_when_absent(recordings: Path) -> None:
    cortex = RecordedCortex.from_directory(recordings)
    expected = 5

    assert asyncio.run(cortex.count_tokens(REQUEST.model, REQUEST.prompt)) == expected
    with pytest.raises(CortexUnavailableError, match="no recorded token count"):
        asyncio.run(cortex.count_tokens(REQUEST.model, "never captured"))


def test_malformed_recording_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(CortexRecordingError):
        RecordedCortex.from_directory(tmp_path)


def test_recording_missing_fields_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "partial.json").write_text('{"model": "m"}', encoding="utf-8")

    with pytest.raises(CortexRecordingError, match="missing fields"):
        RecordedCortex.from_directory(tmp_path)


def test_missing_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CortexRecordingError, match="does not exist"):
        RecordedCortex.from_directory(tmp_path / "absent")


def test_request_validation_rejects_empty_and_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="model must not be empty"):
        CortexRequest(model=" ", prompt="p")
    with pytest.raises(ValueError, match="prompt must not be empty"):
        CortexRequest(model="m", prompt="  ")
    with pytest.raises(ValueError, match="temperature must be between"):
        CortexRequest(model="m", prompt="p", temperature=1.5)
