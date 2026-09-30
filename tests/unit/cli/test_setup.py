from pathlib import Path

import yaml
from click.testing import CliRunner

from cli.setup import setup


def test_setup_prompts_for_and_configures_repositories_root(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    template = tmp_path / "configurations.yaml.example"
    repositories_root = tmp_path / "de-repositories"
    template.write_text(
        "version: 1\nworkspaces:\n  data_engineering:\n    enabled: false\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        setup,
        [
            "--configuration",
            str(configuration),
            "--template",
            str(template),
        ],
        input=f"{repositories_root}\n",
    )

    payload = yaml.safe_load(configuration.read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert f"data-engineering-repositories\t{repositories_root}" in result.output
    assert payload["workspaces"]["data_engineering"]["repositories"]["root"] == str(
        repositories_root
    )
    assert repositories_root.is_dir()


def test_setup_reports_invalid_existing_configuration(tmp_path: Path) -> None:
    configuration = tmp_path / "configurations.yaml"
    configuration.write_text("invalid: [yaml\n", encoding="utf-8")

    result = CliRunner().invoke(
        setup,
        [
            "--repositories-root",
            str(tmp_path / "repositories"),
            "--configuration",
            str(configuration),
        ],
    )

    assert result.exit_code != 0
    assert "user configuration is invalid YAML" in result.output
