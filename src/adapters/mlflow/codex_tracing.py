"""Configure Codex CLI turn tracing for an MLflow tracking server."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

NOTIFY_COMMAND = ["mlflow-codex", "notify-hook"]


class CodexTracingConfigurationError(RuntimeError):
    """Raised when Codex tracing configuration cannot be updated safely."""

    @classmethod
    def empty_tracking_uri(cls) -> CodexTracingConfigurationError:
        """Create an error for an empty tracking URI."""
        return cls("MLflow tracking URI must not be empty")

    @classmethod
    def empty_experiment_id(cls) -> CodexTracingConfigurationError:
        """Create an error for an empty experiment ID."""
        return cls("MLflow experiment ID must not be empty")

    @classmethod
    def invalid_path(cls, path: Path) -> CodexTracingConfigurationError:
        """Create an error for a non-file Codex config path."""
        return cls(f"Codex config path is not a file: {path}")

    @classmethod
    def invalid_toml(
        cls,
        path: Path,
        reason: str,
    ) -> CodexTracingConfigurationError:
        """Create an error for malformed Codex configuration."""
        return cls(f"Codex config is invalid TOML: {path}: {reason}")

    @classmethod
    def notify_conflict(cls, path: Path) -> CodexTracingConfigurationError:
        """Create an error for a pre-existing notification command."""
        return cls(
            f"Codex config already defines a notify hook: {path}; "
            "merge the MLflow hook manually"
        )


@dataclass(frozen=True, slots=True)
class CodexTracingConfiguration:
    """Paths written while enabling MLflow tracing for Codex."""

    codex_config: Path
    tracing_config: Path


@dataclass(frozen=True, slots=True)
class CodexTracingConfigurator:
    """Persist the MLflow notifier and project tracing destination."""

    codex_home: Path
    project_root: Path

    def configure(
        self,
        *,
        tracking_uri: str,
        experiment_id: str,
    ) -> CodexTracingConfiguration:
        """Enable MLflow tracing without replacing an existing notifier."""
        normalized_uri = tracking_uri.strip()
        normalized_experiment = experiment_id.strip()
        if not normalized_uri:
            raise CodexTracingConfigurationError.empty_tracking_uri()
        if not normalized_experiment:
            raise CodexTracingConfigurationError.empty_experiment_id()

        codex_config = self.codex_home / "config.toml"
        tracing_config = self.project_root / ".codex" / "mlflow-tracing.json"
        config_text = _read_codex_config(codex_config)
        updated_text = _add_notify_hook(config_text, codex_config)

        codex_config.parent.mkdir(parents=True, exist_ok=True)
        tracing_config.parent.mkdir(parents=True, exist_ok=True)
        codex_config.write_text(updated_text, encoding="utf-8")
        tracing_config.write_text(
            json.dumps(
                {
                    "trackingUri": normalized_uri,
                    "experimentId": normalized_experiment,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CodexTracingConfiguration(
            codex_config=codex_config,
            tracing_config=tracing_config,
        )


def _read_codex_config(path: Path) -> str:
    if not path.exists():
        return ""
    if not path.is_file():
        raise CodexTracingConfigurationError.invalid_path(path)
    return path.read_text(encoding="utf-8")


def _add_notify_hook(config_text: str, path: Path) -> str:
    try:
        parsed = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as error:
        raise CodexTracingConfigurationError.invalid_toml(path, str(error)) from error
    if "notify" in parsed:
        if parsed["notify"] == NOTIFY_COMMAND:
            return config_text
        raise CodexTracingConfigurationError.notify_conflict(path)

    lines = config_text.splitlines(keepends=True)
    insertion = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("[")),
        len(lines),
    )
    prefix = 'notify = ["mlflow-codex", "notify-hook"]\n'
    if insertion > 0 and lines[insertion - 1].strip():
        prefix += "\n"
    lines.insert(insertion, prefix)
    return "".join(lines)
