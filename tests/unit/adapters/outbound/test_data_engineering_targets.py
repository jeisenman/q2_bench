from adapters.outbound.data_engineering import (
    ADLS_DEV,
    ADLS_PREPROD,
    ADLS_PROD_CA,
    ADLS_PROD_US,
    ADLS_STAGING,
    ADLS_TARGETS,
    DATABRICKS_PROD,
    DATABRICKS_RAPREPROD,
    DATABRICKS_TARGETS,
    INITIATIVE_SMOKE_TESTS,
    OMS_TARGETS,
    SNOWFLAKE_TARGETS,
    SnowflakeAccessMode,
    SnowflakeEnvironment,
)

EXPECTED_INITIATIVE_COUNT = 6


def test_databricks_targets_use_requested_workspaces() -> None:
    assert DATABRICKS_RAPREPROD.name == "pl-databricks-us-rapreprod-01"
    assert DATABRICKS_RAPREPROD.workspace_id == "7628572648057993"
    assert DATABRICKS_RAPREPROD.sql_warehouse_id is None
    assert DATABRICKS_PROD.name == "pl-databricks-us-prod-01"
    assert DATABRICKS_PROD.workspace_id == "3510128597187204"
    assert DATABRICKS_PROD.sql_warehouse_id == "434de6917eea68b6"
    assert DATABRICKS_TARGETS == {
        "data_engineering": DATABRICKS_PROD,
        "ra": DATABRICKS_RAPREPROD,
    }


def test_snowflake_supports_python_and_cortex_in_each_environment() -> None:
    assert {target.environment for target in SNOWFLAKE_TARGETS} == set(
        SnowflakeEnvironment
    )
    assert all(
        target.access_modes
        == {
            SnowflakeAccessMode.PYTHON_CONNECTOR,
            SnowflakeAccessMode.CORTEX,
        }
        for target in SNOWFLAKE_TARGETS
    )


def test_adls_targets_cover_every_requested_location() -> None:
    assert ADLS_DEV.account_name == "pladls2usdatamartdev"
    assert ADLS_STAGING.account_name == "pladls2usdatamartpreprod"
    assert ADLS_PREPROD is ADLS_STAGING
    assert ADLS_PROD_US.account_name == "pladls2usdatamartprod"
    assert ADLS_PROD_CA.account_name == "pladls2cacdatamartprod"
    assert set(ADLS_TARGETS.values()) == {
        ADLS_DEV,
        ADLS_STAGING,
        ADLS_PROD_US,
        ADLS_PROD_CA,
    }


def test_oms_targets_are_the_two_primary_production_workspaces() -> None:
    assert {target.workspace_name for target in OMS_TARGETS.values()} == {
        "pl-oms-us-primary",
        "pl-oms-ca-primary",
    }


def test_every_dataeng_initiative_has_a_smoke_test_target() -> None:
    assert len(INITIATIVE_SMOKE_TESTS) == EXPECTED_INITIATIVE_COUNT
    assert (
        len({item.initiative_id for item in INITIATIVE_SMOKE_TESTS})
        == EXPECTED_INITIATIVE_COUNT
    )
    assert all(item.source_paths for item in INITIATIVE_SMOKE_TESTS)
    assert all(
        item.requires_databricks or item.requires_snowflake or item.requires_adls
        for item in INITIATIVE_SMOKE_TESTS
    )
