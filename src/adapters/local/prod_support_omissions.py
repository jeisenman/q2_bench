"""Private local persistence for production-support omission settings."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from workspaces.data_engineering.workflows.prod_support.reporting_config import (
    DEFAULT_DATA_INTERNAL_OMISSIONS,
    ProdSupportReportConfig,
)

PROD_SUPPORT_HOME_ENV = "PROD_SUPPORT_HOME"
OMISSIONS_FILENAME = "omissions.json"
SCHEMA_VERSION = 1


class ProdSupportOmissionsError(ValueError):
    """Raised when the local omissions file is invalid."""

    @classmethod
    def invalid_json(cls, path: Path) -> ProdSupportOmissionsError:
        """Return an invalid-JSON error."""
        return cls(f"{path}: omissions file must contain valid JSON")

    @classmethod
    def object_required(cls, path: Path) -> ProdSupportOmissionsError:
        """Return a top-level object error."""
        return cls(f"{path}: expected a JSON object")

    @classmethod
    def invalid_schema(cls, path: Path) -> ProdSupportOmissionsError:
        """Return a schema-version error."""
        return cls(f"{path}: schema_version must be {SCHEMA_VERSION}")

    @classmethod
    def list_required(cls, path: Path) -> ProdSupportOmissionsError:
        """Return an omission-list error."""
        return cls(f"{path}: data_internal_omissions must be a list")

    @classmethod
    def invalid_values(
        cls,
        path: Path,
        error: ValueError,
    ) -> ProdSupportOmissionsError:
        """Return a validated-value error."""
        return cls(f"{path}: {error}")


class JsonProdSupportOmissionStore:
    """Store production-support omission settings in private JSON."""

    def __init__(self, root: Path | None = None) -> None:
        """Initialize with an explicit root or the standard user directory."""
        configured = os.environ.get(PROD_SUPPORT_HOME_ENV)
        self._root = (
            root
            if root is not None
            else Path(configured).expanduser()
            if configured
            else Path.home() / ".prod_support"
        )

    @property
    def path(self) -> Path:
        """Return the omissions JSON path."""
        return self._root / OMISSIONS_FILENAME

    def ensure(self) -> Path:
        """Create the private directory and default file when absent."""
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._root.chmod(0o700)
        if not self.path.exists():
            self.save(tuple(item.value for item in DEFAULT_DATA_INTERNAL_OMISSIONS))
        return self.path

    def load(self) -> ProdSupportReportConfig:
        """Load and validate omission settings, creating defaults if needed."""
        path = self.ensure()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ProdSupportOmissionsError.invalid_json(path) from error
        if not isinstance(raw, dict):
            raise ProdSupportOmissionsError.object_required(path)
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ProdSupportOmissionsError.invalid_schema(path)
        values = raw.get("data_internal_omissions")
        if not isinstance(values, list):
            raise ProdSupportOmissionsError.list_required(path)
        try:
            return ProdSupportReportConfig.from_omission_values(values)
        except ValueError as error:
            raise ProdSupportOmissionsError.invalid_values(path, error) from error

    def save(self, values: Sequence[str]) -> ProdSupportReportConfig:
        """Validate and persist omission settings with private permissions."""
        config = ProdSupportReportConfig.from_omission_values(values)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._root.chmod(0o700)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "data_internal_omissions": [
                item.value for item in config.data_internal_omissions
            ],
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.path.chmod(0o600)
        return config
