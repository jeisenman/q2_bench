from pathlib import Path

import yaml

ROOT = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks"
    / "production_support/dates"
)
SNAPSHOTS = (ROOT / "09-25-26", ROOT / "09-26-26")


def _load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _schema(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _schema(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        item_schemas = tuple(_schema(item) for item in value)
        if not item_schemas:
            return ("list", ())
        first = item_schemas[0]
        assert all(item == first for item in item_schemas)
        return ("list", first)
    return type(value).__name__


def test_capability_snapshots_have_identical_file_and_document_schemas() -> None:
    capability_sets = tuple(
        {path.name for path in (snapshot / "capabilities").glob("*.yaml")}
        for snapshot in SNAPSHOTS
    )

    assert capability_sets[0] == capability_sets[1]
    for filename in sorted(capability_sets[0]):
        left = _load(SNAPSHOTS[0] / "capabilities" / filename)
        right = _load(SNAPSHOTS[1] / "capabilities" / filename)
        assert _schema(left) == _schema(right), filename


def test_suite_snapshots_register_identical_capability_contracts() -> None:
    left = _load(SNAPSHOTS[0] / "suite.yaml")
    right = _load(SNAPSHOTS[1] / "suite.yaml")

    assert isinstance(left, dict)
    assert isinstance(right, dict)
    assert _schema(left) == _schema(right)
    left_layers = left["layers"]
    right_layers = right["layers"]
    assert (
        left_layers["capabilities"]["fixtures"]
        == (right_layers["capabilities"]["fixtures"])
    )
    assert (
        left_layers["capabilities"]["dimensions"]
        == (right_layers["capabilities"]["dimensions"])
    )
    assert (
        left_layers["coordination"]["dimensions"]
        == (right_layers["coordination"]["dimensions"])
    )
