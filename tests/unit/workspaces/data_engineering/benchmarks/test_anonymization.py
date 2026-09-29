from uuid import UUID

import pytest

from workspaces.data_engineering.benchmarks.anonymization import (
    AnonymizationError,
    AnonymizationPolicy,
    ColumnPolicy,
    Strategy,
    anonymize_rows,
    anonymize_value,
    load_policy,
)

COLUMNS = ("client_id", "client_code", "failed_at", "note", "row_count")
ROWS = (
    (
        "a1b2c3d4-0000-4000-8000-000000000001",
        "Scotiabank",
        "2026-09-26T05:14:22Z",
        "contains customer detail",
        "142",
    ),
    (
        "a1b2c3d4-0000-4000-8000-000000000001",
        "Scotiabank",
        "2026-09-26T06:00:00Z",
        "more detail",
        "7",
    ),
)


def policy(salt: str = "case-salt") -> AnonymizationPolicy:
    return AnonymizationPolicy(
        salt=salt,
        columns=(
            ColumnPolicy("client_id", Strategy.UUID),
            ColumnPolicy("client_code", Strategy.PSEUDONYM),
            ColumnPolicy("failed_at", Strategy.GENERALIZE),
            ColumnPolicy("note", Strategy.REDACT),
            ColumnPolicy("row_count", Strategy.KEEP),
        ),
    )


def test_same_input_and_salt_always_produce_the_same_fixture() -> None:
    assert anonymize_rows(COLUMNS, ROWS, policy()) == anonymize_rows(
        COLUMNS, ROWS, policy()
    )


def test_one_identifier_maps_to_one_pseudonym_so_joins_still_work() -> None:
    result = anonymize_rows(COLUMNS, ROWS, policy())

    assert result[0][0] == result[1][0]
    assert result[0][1] == result[1][1]


def test_a_different_salt_produces_different_pseudonyms() -> None:
    first = anonymize_rows(COLUMNS, ROWS, policy("salt-a"))
    second = anonymize_rows(COLUMNS, ROWS, policy("salt-b"))

    assert first[0][0] != second[0][0]


def test_original_values_do_not_survive() -> None:
    result = anonymize_rows(COLUMNS, ROWS, policy())
    rendered = str(result)

    assert "Scotiabank" not in rendered
    assert "a1b2c3d4-0000-4000-8000-000000000001" not in rendered
    assert "contains customer detail" not in rendered


def test_pseudonyms_preserve_length_and_character_class() -> None:
    result = anonymize_rows(COLUMNS, ROWS, policy())
    code = result[0][1]

    assert code is not None
    assert len(code) == len("Scotiabank")
    assert code[0].isupper()
    assert code.isalpha()


def test_uuid_pseudonyms_are_valid_uuids() -> None:
    result = anonymize_rows(COLUMNS, ROWS, policy())

    assert str(UUID(str(result[0][0]))) == result[0][0]


def test_generalize_reduces_a_timestamp_to_its_date() -> None:
    result = anonymize_rows(COLUMNS, ROWS, policy())

    assert result[0][2] == "2026-09-26"
    assert result[1][2] == "2026-09-26"


def test_keep_preserves_non_identifying_values() -> None:
    result = anonymize_rows(COLUMNS, ROWS, policy())

    assert result[0][4] == "142"


def test_nulls_stay_null_under_every_strategy() -> None:
    for strategy in Strategy:
        assert anonymize_value(None, strategy, salt="s", column="c") is None


def test_an_undeclared_column_is_an_error_not_a_silent_keep() -> None:
    with pytest.raises(AnonymizationError, match="undeclared: extra"):
        anonymize_rows(
            (*COLUMNS, "extra"),
            ((*ROWS[0], "leaked"),),
            policy(),
        )


def test_a_policy_for_a_missing_column_is_rejected() -> None:
    with pytest.raises(AnonymizationError, match="unknown column"):
        anonymize_rows(COLUMNS[:2], (ROWS[0][:2],), policy())


def test_empty_salt_is_rejected() -> None:
    with pytest.raises(AnonymizationError, match="salt must not be empty"):
        AnonymizationPolicy(salt="  ", columns=())


def test_uuid_strategy_rejects_a_non_uuid_value() -> None:
    with pytest.raises(AnonymizationError, match="not a UUID"):
        anonymize_value("not-a-uuid", Strategy.UUID, salt="s", column="client_id")


def test_policy_loads_from_a_case_declaration() -> None:
    loaded = load_policy(
        {"columns": {"client_id": "uuid", "note": "redact"}},
        salt="case-salt",
    )

    assert loaded.strategy_for("client_id") is Strategy.UUID
    assert loaded.strategy_for("note") is Strategy.REDACT


def test_empty_declaration_is_rejected() -> None:
    with pytest.raises(AnonymizationError, match="non-empty mapping"):
        load_policy({"columns": {}}, salt="case-salt")
