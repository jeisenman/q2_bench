"""Tests for conversational production-support omission settings."""

import pytest

from workspaces.data_engineering.agents.prod_support.reporting_config import (
    update_omission_values,
)


def test_conversational_omission_updates_add_and_remove_codes() -> None:
    assert update_omission_values(("d2p",), "add subscriber and CMM") == (
        "d2p",
        "subscriber",
        "cmm",
    )
    assert update_omission_values(
        ("d2p", "subscriber", "cmm"),
        "remove D2P and subscriber",
    ) == ("cmm",)


def test_conversational_omission_update_requires_one_operation() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        update_omission_values(("d2p",), "add and remove d2p")
