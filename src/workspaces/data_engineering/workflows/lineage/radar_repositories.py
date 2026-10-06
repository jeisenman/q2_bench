"""Explicit local checkout paths for aggregate RADAR lineage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RadarRepositories:
    """Local source checkouts required for aggregate RADAR lineage."""

    di_pipelines: Path
    radar_notebooks: Path
    radar_libraries: Path
    radar_adf: Path
    data_ingress: Path
    calculation_engine: Path

    def as_mapping(self) -> dict[str, Path]:
        """Return stable component names and checkout paths."""
        return {
            "di-pipelines": self.di_pipelines,
            "radar-notebooks": self.radar_notebooks,
            "radar-libraries": self.radar_libraries,
            "radar-adf-pipeline": self.radar_adf,
            "pl-dataingress": self.data_ingress,
            "pl-calculation-engine": self.calculation_engine,
        }
