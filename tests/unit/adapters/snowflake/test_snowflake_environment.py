import pytest

from adapters.snowflake.environment import (
    AUTHENTICATOR_SUFFIX,
    DEFAULT_AUTHENTICATOR,
    EXTERNAL_BROWSER,
    SETTING_SUFFIXES,
    SnowflakeConfigurationError,
    load_settings,
    variable_name,
)
from adapters.snowflake.warehouse import ReadOnlyViolationError, require_read_only
from domain.environments import Environment, UnknownEnvironmentError


def configure(monkeypatch: pytest.MonkeyPatch, environment: Environment) -> None:
    for suffix in SETTING_SUFFIXES:
        monkeypatch.setenv(
            variable_name(environment, suffix), f"{suffix.lower()}-value"
        )


@pytest.mark.parametrize(
    "environment", [Environment.DEV, Environment.STAGE, Environment.PROD]
)
def test_each_environment_reads_its_own_variables(
    monkeypatch: pytest.MonkeyPatch,
    environment: Environment,
) -> None:
    configure(monkeypatch, environment)

    settings = load_settings(environment)

    assert settings.environment is environment
    assert settings.account == "account-value"


def test_environments_do_not_share_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)

    with pytest.raises(SnowflakeConfigurationError, match="SNOWFLAKE_PROD_ACCOUNT"):
        load_settings(Environment.PROD)


def test_missing_settings_name_every_variable_to_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for suffix in SETTING_SUFFIXES:
        monkeypatch.delenv(variable_name(Environment.STAGE, suffix), raising=False)

    with pytest.raises(SnowflakeConfigurationError) as caught:
        load_settings(Environment.STAGE)

    for suffix in SETTING_SUFFIXES:
        assert variable_name(Environment.STAGE, suffix) in str(caught.value)


def test_sandbox_has_no_snowflake_connection() -> None:
    with pytest.raises(SnowflakeConfigurationError, match="served by DuckDB"):
        load_settings(Environment.SANDBOX)


def test_secret_reference_defaults_per_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.PROD)
    monkeypatch.delenv(variable_name(Environment.PROD, "SECRET_REF"), raising=False)

    assert load_settings(Environment.PROD).secret_ref == "snowflake/prod/password"


def test_password_is_supplied_at_call_time_not_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)
    settings = load_settings(Environment.DEV)

    assert "password" not in {
        field for field in dir(settings) if not field.startswith("_")
    }
    assert settings.connection_arguments("secret-value")["password"] == "secret-value"


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO t VALUES (1)",
        "  update t SET n = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "MERGE INTO t USING s ON t.id = s.id",
        "TRUNCATE TABLE t",
        "GRANT SELECT ON t TO ROLE r",
    ],
)
def test_write_statements_are_rejected(statement: str) -> None:
    with pytest.raises(ReadOnlyViolationError):
        require_read_only(statement)


@pytest.mark.parametrize(
    "statement",
    ["SELECT 1", "  select n from t", "WITH x AS (SELECT 1) SELECT * FROM x"],
)
def test_reads_are_allowed(statement: str) -> None:
    require_read_only(statement)


def test_environment_parsing_is_case_insensitive_and_fails_loudly() -> None:
    assert Environment.parse("  PROD ") is Environment.PROD
    assert Environment.parse("sandbox") is Environment.SANDBOX
    with pytest.raises(UnknownEnvironmentError, match="supported"):
        Environment.parse("production")


def test_only_sandbox_is_deterministic() -> None:
    assert Environment.SANDBOX.is_deterministic is True
    assert all(
        not item.is_deterministic
        for item in Environment
        if item is not Environment.SANDBOX
    )


def test_default_authenticator_is_snowflake_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)
    monkeypatch.delenv(
        variable_name(Environment.DEV, AUTHENTICATOR_SUFFIX), raising=False
    )

    settings = load_settings(Environment.DEV)

    assert settings.authenticator == DEFAULT_AUTHENTICATOR
    assert settings.requires_secret is True
    assert "authenticator" not in settings.connection_arguments("secret-value")


def test_external_browser_needs_no_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)
    monkeypatch.setenv(
        variable_name(Environment.DEV, AUTHENTICATOR_SUFFIX), EXTERNAL_BROWSER
    )

    settings = load_settings(Environment.DEV)

    assert settings.requires_secret is False
    arguments = settings.connection_arguments(None)
    assert arguments["authenticator"] == EXTERNAL_BROWSER
    assert "password" not in arguments


def test_okta_account_url_is_accepted_and_still_needs_a_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)
    monkeypatch.setenv(
        variable_name(Environment.DEV, AUTHENTICATOR_SUFFIX),
        "https://example.okta.com",
    )

    settings = load_settings(Environment.DEV)

    assert settings.requires_secret is True
    arguments = settings.connection_arguments("secret-value")
    assert arguments["authenticator"] == "https://example.okta.com"
    assert arguments["password"] == "secret-value"


def test_unknown_authenticator_is_rejected_with_the_allowed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)
    monkeypatch.setenv(variable_name(Environment.DEV, AUTHENTICATOR_SUFFIX), "okta-sso")

    with pytest.raises(SnowflakeConfigurationError, match="externalbrowser"):
        load_settings(Environment.DEV)


def test_password_mode_without_a_secret_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, Environment.DEV)
    settings = load_settings(Environment.DEV)

    with pytest.raises(SnowflakeConfigurationError, match="needs a password"):
        settings.connection_arguments(None)
