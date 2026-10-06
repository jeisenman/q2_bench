"""Static ADF, DataIngress, and engine calculation evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.enrichments import (
    SourceLocation,
)

_METHOD = re.compile(r"\b(Calculate[A-Za-z0-9_]+)\s*\(")


@dataclass(frozen=True, slots=True)
class EngineCalculation:
    """One public RADAR calculation contract exposed by the engine."""

    service: str
    method: str
    sources: tuple[SourceLocation, ...]


def engine_calculations(repository: Path) -> tuple[EngineCalculation, ...]:
    """Read public Calculate methods from RADAR engine service interfaces."""
    interface_root = (
        repository / "PrecisionLender.Common.Engine.EngineService/Interfaces"
    )
    calculations: list[EngineCalculation] = []
    for path in sorted(interface_root.glob("IRA*EngineService.cs")):
        service = path.stem
        implementation = (
            repository
            / "PrecisionLender.Common.Engine.EngineService"
            / f"{service.removeprefix('I')}.cs"
        )
        implementation_lines = (
            implementation.read_text(encoding="utf-8-sig").splitlines()
            if implementation.is_file()
            else []
        )
        relative = path.relative_to(repository).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(),
            start=1,
        ):
            match = _METHOD.search(line)
            if match is None:
                continue
            method = match.group(1)
            sources = [SourceLocation(f"pl-calculation-engine/{relative}", line_number)]
            implementation_line = _matching_line(implementation_lines, method)
            if implementation_line is not None:
                implementation_relative = implementation.relative_to(
                    repository
                ).as_posix()
                sources.append(
                    SourceLocation(
                        f"pl-calculation-engine/{implementation_relative}",
                        implementation_line,
                    )
                )
            calculations.append(EngineCalculation(service, method, tuple(sources)))
    return tuple(sorted(calculations, key=lambda item: (item.service, item.method)))


def adf_activity_sources(
    repository: Path,
    activities: tuple[str, ...],
) -> tuple[SourceLocation, ...]:
    """Find named ADF activities and retain their exact source lines."""
    requested = set(activities)
    sources: list[SourceLocation] = []
    for path in sorted((repository / "pipeline").glob("*.json")):
        relative = path.relative_to(repository).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if '"name":' not in line:
                continue
            if not any(f'"name": "{name}"' in line for name in requested):
                continue
            sources.append(
                SourceLocation(
                    f"radar-adf-pipeline/{relative}",
                    line_number,
                )
            )
    return tuple(sorted(set(sources), key=lambda item: (item.path, item.line)))


def text_source(
    repository: Path,
    prefix: str,
    relative: Path,
    needle: str,
) -> SourceLocation:
    """Locate required source text and fail when the contract disappears."""
    path = repository / relative
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        if needle in line:
            return SourceLocation(f"{prefix}/{relative.as_posix()}", line_number)
    message = f"required lineage source text was not found: {relative}: {needle}"
    raise ValueError(message)


def _matching_line(lines: list[str], method: str) -> int | None:
    for line_number, line in enumerate(lines, start=1):
        if re.search(rf"\b{re.escape(method)}\s*\(", line):
            return line_number
    return None
