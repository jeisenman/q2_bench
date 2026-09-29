import pytest

from domain.sql_portability import (
    SqlPortabilityError,
    is_cortex_call,
    portability_violations,
    require_portable,
)

PORTABLE = "SELECT client_code FROM analytics.failed_jobs ORDER BY client_code"


def test_portable_statement_passes() -> None:
    require_portable(PORTABLE)
    assert portability_violations(PORTABLE) == ()


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        ("SELECT SNOWFLAKE.CORTEX.COMPLETE('m', p) FROM t", "cortex_call"),
        ("SELECT payload:region FROM t", "variant_colon_path"),
        (
            "SELECT v.value FROM t, LATERAL FLATTEN(input => t.tags) v",
            "lateral_flatten",
        ),
        ("SELECT OBJECT_CONSTRUCT('k', n) FROM t", "object_construct"),
        ("SELECT DATEADD(day, 1, ts) FROM t", "dateadd_bare_part"),
        ("SELECT * FROM t WHERE ts > CURRENT_TIMESTAMP", "nondeterministic_clock"),
        ("SELECT RANDOM() FROM t", "nondeterministic_value"),
    ],
)
def test_unportable_constructs_are_rejected(statement: str, rule: str) -> None:
    with pytest.raises(SqlPortabilityError) as caught:
        require_portable(statement)
    assert any(violation.startswith(rule) for violation in caught.value.violations)


def test_violation_names_the_portable_alternative() -> None:
    with pytest.raises(SqlPortabilityError) as caught:
        require_portable("SELECT payload:region FROM t")
    assert "payload->>'region'" in str(caught.value)


def test_cortex_violation_points_at_the_cortex_port() -> None:
    with pytest.raises(SqlPortabilityError) as caught:
        require_portable("SELECT SNOWFLAKE.CORTEX.SENTIMENT(note) FROM t")
    assert "CortexInference port" in str(caught.value)


def test_constructs_inside_string_literals_are_not_flagged() -> None:
    # A row whose text mentions a construct is data, not SQL.
    require_portable("SELECT * FROM t WHERE note = 'see LATERAL FLATTEN docs'")
    require_portable("SELECT 'payload:region' AS example FROM t")


def test_constructs_inside_comments_are_not_flagged() -> None:
    require_portable("SELECT n FROM t -- avoid CURRENT_TIMESTAMP here")
    require_portable("SELECT n FROM t /* OBJECT_CONSTRUCT was removed */")


def test_multiple_violations_are_all_reported() -> None:
    with pytest.raises(SqlPortabilityError) as caught:
        require_portable("SELECT payload:region, RANDOM() FROM t WHERE ts < NOW()")
    expected = 3
    assert len(caught.value.violations) == expected


def test_empty_statement_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        require_portable("   ")


def test_is_cortex_call_detects_the_namespace() -> None:
    assert is_cortex_call("SELECT SNOWFLAKE.CORTEX.COMPLETE('m','p')") is True
    assert is_cortex_call("SELECT 1") is False
    assert is_cortex_call("SELECT 'SNOWFLAKE.CORTEX.COMPLETE'") is False
