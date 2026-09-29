"""Replay recorded Cortex responses in the sandbox environment.

Cortex cannot be reproduced the way CSV fixtures reproduce table data, so the
sandbox double replays responses captured from a real environment. A request
that was never recorded fails loudly rather than inventing a completion,
because a fabricated model answer inside a benchmark is worse than a missing
one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from domain.environments import Environment
from ports.cortex import (
    CortexError,
    CortexRequest,
    CortexResponse,
    CortexUnavailableError,
)


class CortexRecordingError(CortexError):
    """Raised when a recorded Cortex fixture cannot be used."""

    @classmethod
    def not_recorded(cls, key: str, request: CortexRequest) -> CortexRecordingError:
        """Return an error naming the missing recording and how to create it."""
        return cls(
            f"no recorded Cortex response for {request.model!r} (key {key}). "
            "Capture one against a real environment with CortexRecorder before "
            "using it in a sandbox run."
        )

    @classmethod
    def malformed(cls, path: Path, reason: str) -> CortexRecordingError:
        """Return an error identifying a malformed recording file."""
        return cls(f"{path}: {reason}")


def recording_key(request: CortexRequest) -> str:
    """Return the stable key identifying one Cortex request."""
    payload = json.dumps(
        {
            "model": request.model,
            "prompt": request.prompt,
            "temperature": request.temperature,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class CortexRecording:
    """One captured Cortex response."""

    key: str
    model: str
    prompt: str
    temperature: float
    text: str
    token_count: int


class RecordedCortex:
    """Serve Cortex completions from recordings captured earlier."""

    def __init__(self, recordings: tuple[CortexRecording, ...]) -> None:
        """Index recordings by their request key."""
        self._recordings = {item.key: item for item in recordings}

    @classmethod
    def from_directory(cls, root: Path) -> RecordedCortex:
        """Load every ``*.json`` recording beneath a fixture directory."""
        if not root.is_dir():
            message = f"Cortex recording directory does not exist: {root}"
            raise CortexRecordingError(message)
        return cls(tuple(_read_recording(path) for path in sorted(root.glob("*.json"))))

    @property
    def environment(self) -> Environment:
        """Return the sandbox environment."""
        return Environment.SANDBOX

    async def complete(self, request: CortexRequest) -> CortexResponse:
        """Return the recorded completion, or fail when none was captured."""
        key = recording_key(request)
        recording = self._recordings.get(key)
        if recording is None:
            raise CortexRecordingError.not_recorded(key, request)
        return CortexResponse(
            text=recording.text,
            model=recording.model,
            environment=Environment.SANDBOX,
            recorded=True,
        )

    async def count_tokens(self, model: str, text: str) -> int:
        """Return the recorded token count for a captured request."""
        key = recording_key(CortexRequest(model=model, prompt=text))
        recording = self._recordings.get(key)
        if recording is None:
            message = (
                f"no recorded token count for {model!r}; "
                "capture one against a real environment first"
            )
            raise CortexUnavailableError(message)
        return recording.token_count


def _read_recording(path: Path) -> CortexRecording:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CortexRecordingError.malformed(path, str(error)) from error
    if not isinstance(raw, dict):
        raise CortexRecordingError.malformed(path, "recording must be an object")
    missing = {"model", "prompt", "text"}.difference(raw)
    if missing:
        fields = ", ".join(sorted(missing))
        raise CortexRecordingError.malformed(path, f"missing fields: {fields}")
    request = CortexRequest(
        model=str(raw["model"]),
        prompt=str(raw["prompt"]),
        temperature=float(raw.get("temperature", 0.0)),
    )
    return CortexRecording(
        key=recording_key(request),
        model=request.model,
        prompt=request.prompt,
        temperature=request.temperature,
        text=str(raw["text"]),
        token_count=int(raw.get("token_count", 0)),
    )


def write_recording(
    root: Path, request: CortexRequest, response: str, tokens: int
) -> Path:
    """Persist one captured Cortex response for later sandbox replay."""
    root.mkdir(parents=True, exist_ok=True)
    key = recording_key(request)
    path = root / f"{key}.json"
    path.write_text(
        json.dumps(
            {
                "model": request.model,
                "prompt": request.prompt,
                "temperature": request.temperature,
                "text": response,
                "token_count": tokens,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
