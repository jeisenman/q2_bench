from pathlib import Path

import pytest
import yaml

from adapters.local.configuration import (
    UserConfigurationError,
    configure_data_engineering_repositories,
    data_engineering_repositories_root,
    load_configuration,
)


def _write_template(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "workspaces": {
                    "data_engineering": {
                        "enabled": False,
                        "databricks": {"ra": {"enabled": False}},
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_configure_repositories_creates_root_and_preserves_settings(
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "configurations.yaml"
    template = tmp_path / "configurations.yaml.example"
    repositories_root = tmp_path / "source" / "de"
    _write_template(template)

    configured = configure_data_engineering_repositories(
        repositories_root,
        path=configuration,
        template_path=template,
    )

    payload = yaml.safe_load(configuration.read_text(encoding="utf-8"))
    assert configured == repositories_root
    assert repositories_root.is_dir()
    assert payload["workspaces"]["data_engineering"]["enabled"] is False
    assert payload["workspaces"]["data_engineering"]["databricks"] == {
        "ra": {"enabled": False}
    }
    assert payload["workspaces"]["data_engineering"]["repositories"] == {
        "root": str(repositories_root)
    }
    assert data_engineering_repositories_root(configuration) == repositories_root


def test_configure_repositories_updates_an_existing_configuration(
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "configurations.yaml"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    configuration.write_text(
        "version: 1\nworkspaces:\n  data_engineering:\n"
        f"    repositories:\n      root: {first_root}\n",
        encoding="utf-8",
    )

    configure_data_engineering_repositories(second_root, path=configuration)

    assert data_engineering_repositories_root(configuration) == second_root


def test_configure_repositories_rejects_malformed_configuration(
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "configurations.yaml"
    configuration.write_text("workspaces: []\n", encoding="utf-8")

    with pytest.raises(UserConfigurationError, match="version must be 1"):
        configure_data_engineering_repositories(
            tmp_path / "repositories",
            path=configuration,
        )


def test_configure_repositories_rejects_file_as_root(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    template = tmp_path / "configurations.yaml.example"
    repositories_root = tmp_path / "not-a-directory"
    repositories_root.write_text("content", encoding="utf-8")
    _write_template(template)

    with pytest.raises(UserConfigurationError, match="is not a directory"):
        configure_data_engineering_repositories(
            repositories_root,
            path=configuration,
            template_path=template,
        )


def test_load_configuration_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(UserConfigurationError, match="does not exist"):
        load_configuration(tmp_path / "missing.yaml")


def test_load_configuration_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    configuration.write_text("- version\n- 1\n", encoding="utf-8")

    with pytest.raises(UserConfigurationError, match="top-level mapping"):
        load_configuration(configuration)


def test_read_repositories_root_requires_nested_mappings(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    configuration.write_text("version: 1\nworkspaces: []\n", encoding="utf-8")

    with pytest.raises(UserConfigurationError, match="workspaces must be a mapping"):
        data_engineering_repositories_root(configuration)


def test_read_repositories_root_requires_non_empty_path(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    configuration.write_text(
        "version: 1\nworkspaces:\n  data_engineering:\n"
        "    repositories:\n      root: ''\n",
        encoding="utf-8",
    )

    with pytest.raises(UserConfigurationError, match="must be a non-empty path"):
        data_engineering_repositories_root(configuration)


def test_configure_repositories_requires_template_for_new_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(UserConfigurationError, match="template does not exist"):
        configure_data_engineering_repositories(
            tmp_path / "repositories",
            path=tmp_path / "configurations.yaml",
            template_path=tmp_path / "missing.example",
        )
