"""Read and update per-user repository configuration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

CONFIGURATION_VERSION = 1
DEFAULT_CONFIGURATION_PATH = Path("configurations.yaml")
DEFAULT_CONFIGURATION_TEMPLATE = Path("configurations.yaml.example")
DEFAULT_DATA_ENGINEERING_REPOSITORIES_ROOT = Path.home() / "ra"


class UserConfigurationError(ValueError):
    """Raised when the per-user configuration cannot be read or updated."""

    @classmethod
    def missing_configuration(cls, path: Path) -> UserConfigurationError:
        """Return an error for an absent user configuration."""
        return cls(f"user configuration does not exist: {path}")

    @classmethod
    def invalid_yaml(cls, path: Path) -> UserConfigurationError:
        """Return an error for malformed YAML."""
        return cls(f"user configuration is invalid YAML: {path}")

    @classmethod
    def invalid_root(cls, path: Path) -> UserConfigurationError:
        """Return an error for a non-mapping YAML root."""
        return cls(f"user configuration must contain a top-level mapping: {path}")

    @classmethod
    def invalid_version(cls, path: Path) -> UserConfigurationError:
        """Return an error for an unsupported configuration version."""
        return cls(f"{path}: version must be {CONFIGURATION_VERSION}")

    @classmethod
    def missing_repository_root(cls, path: Path) -> UserConfigurationError:
        """Return an error for an absent DE repository-root path."""
        return cls(
            f"{path}: workspaces.data_engineering.repositories.root "
            "must be a non-empty path"
        )

    @classmethod
    def missing_contx_repository(cls, path: Path) -> UserConfigurationError:
        """Return an error for an absent Contx repository path."""
        return cls(
            f"{path}: workspaces.data_engineering.repositories.contx "
            "must be a non-empty path"
        )

    @classmethod
    def repository_root_is_file(cls, path: Path) -> UserConfigurationError:
        """Return an error when the selected repository root is a file."""
        return cls(f"Data Engineering repositories root is not a directory: {path}")

    @classmethod
    def missing_template(cls, path: Path) -> UserConfigurationError:
        """Return an error for an absent configuration template."""
        return cls(f"configuration template does not exist: {path}")

    @classmethod
    def mapping_required(cls, path: Path, key: str) -> UserConfigurationError:
        """Return an error for a key that should contain a mapping."""
        return cls(f"{path}: {key} must be a mapping")


def load_configuration(path: Path = DEFAULT_CONFIGURATION_PATH) -> dict[str, Any]:
    """Load a validated top-level per-user configuration mapping."""
    if not path.is_file():
        raise UserConfigurationError.missing_configuration(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise UserConfigurationError.invalid_yaml(path) from error
    return _validated_configuration(raw, path)


def data_engineering_repositories_root(
    path: Path = DEFAULT_CONFIGURATION_PATH,
) -> Path:
    """Return the configured parent directory for DE repository checkouts."""
    configuration = load_configuration(path)
    workspaces = _required_mapping(configuration, "workspaces", path)
    data_engineering = _required_mapping(workspaces, "data_engineering", path)
    repositories = _required_mapping(data_engineering, "repositories", path)
    root = repositories.get("root")
    if not isinstance(root, str) or not root.strip():
        raise UserConfigurationError.missing_repository_root(path)
    return Path(root).expanduser()


def data_engineering_contx_repository(
    path: Path = DEFAULT_CONFIGURATION_PATH,
) -> Path:
    """Return the configured Contx repository checkout."""
    configuration = load_configuration(path)
    workspaces = _required_mapping(configuration, "workspaces", path)
    data_engineering = _required_mapping(workspaces, "data_engineering", path)
    repositories = _required_mapping(data_engineering, "repositories", path)
    contx = repositories.get("contx")
    if not isinstance(contx, str) or not contx.strip():
        raise UserConfigurationError.missing_contx_repository(path)
    return Path(contx).expanduser()


def configure_data_engineering_repositories(
    repositories_root: Path,
    *,
    path: Path = DEFAULT_CONFIGURATION_PATH,
    template_path: Path = DEFAULT_CONFIGURATION_TEMPLATE,
) -> Path:
    """Persist and create the parent directory for local DE repositories."""
    expanded_root = repositories_root.expanduser()
    if expanded_root.exists() and not expanded_root.is_dir():
        raise UserConfigurationError.repository_root_is_file(expanded_root)

    configuration = (
        load_configuration(path)
        if path.exists()
        else _load_template_configuration(template_path)
    )
    workspaces = _mapping_for_update(configuration, "workspaces", path)
    data_engineering = _mapping_for_update(workspaces, "data_engineering", path)
    repositories = _mapping_for_update(data_engineering, "repositories", path)
    repositories["root"] = _display_path(expanded_root)

    expanded_root.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(configuration, sort_keys=False),
        encoding="utf-8",
    )
    return expanded_root


def _load_template_configuration(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise UserConfigurationError.missing_template(path)
    return load_configuration(path)


def _validated_configuration(raw: object, path: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise UserConfigurationError.invalid_root(path)
    version = raw.get("version")
    if version != CONFIGURATION_VERSION:
        raise UserConfigurationError.invalid_version(path)
    return raw


def _required_mapping(
    parent: Mapping[str, Any],
    key: str,
    path: Path,
) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise UserConfigurationError.mapping_required(path, key)
    return value


def _mapping_for_update(
    parent: dict[str, Any],
    key: str,
    path: Path,
) -> dict[str, Any]:
    value = parent.setdefault(key, {})
    if not isinstance(value, dict):
        raise UserConfigurationError.mapping_required(path, key)
    return value


def _display_path(path: Path) -> str:
    home = Path.home()
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if not relative.parts else str(Path("~") / relative)
