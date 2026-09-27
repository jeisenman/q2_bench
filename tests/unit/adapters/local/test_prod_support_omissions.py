import json
from pathlib import Path

import pytest

from adapters.local.prod_support_omissions import (
    JsonProdSupportOmissionStore,
    ProdSupportOmissionsError,
)


def test_store_creates_defaults_and_round_trips_values(tmp_path: Path) -> None:
    store = JsonProdSupportOmissionStore(tmp_path / ".prod_support")

    default = store.load()
    updated = store.save(("d2p", "cmm"))

    assert default.data_internal_omissions[0].value == "d2p"
    assert [item.value for item in updated.data_internal_omissions] == ["d2p", "cmm"]
    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "data_internal_omissions": ["d2p", "cmm"],
    }


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"schema_version": 2, "data_internal_omissions": []}',
        '{"schema_version": 1, "data_internal_omissions": {}}',
        '{"schema_version": 1, "data_internal_omissions": ["unknown"]}',
    ],
)
def test_store_rejects_invalid_files(tmp_path: Path, payload: str) -> None:
    store = JsonProdSupportOmissionStore(tmp_path / ".prod_support")
    store.ensure()
    store.path.write_text(payload, encoding="utf-8")

    with pytest.raises(ProdSupportOmissionsError):
        store.load()
