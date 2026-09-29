"""Non-secret targets for data-engineering outbound adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SnowflakeEnvironment(StrEnum):
    """Supported Snowflake deployment environments."""

    ALPHA = "alpha"
    STAGING = "staging"
    PROD_US = "prod_us"


class SnowflakeAccessMode(StrEnum):
    """Supported Snowflake integration mechanisms."""

    PYTHON_CONNECTOR = "python_connector"
    CORTEX = "cortex"


class AdlsEnvironment(StrEnum):
    """Supported ADLS deployment locations."""

    DEV = "dev"
    STAGING = "staging"
    PROD_US = "prod_us"
    PROD_CA = "prod_ca"


class OmsRegion(StrEnum):
    """Supported production OMS regions."""

    US = "us"
    CA = "ca"


@dataclass(frozen=True, slots=True)
class DatabricksTarget:
    """A named Databricks workspace with an optional SQL warehouse."""

    name: str
    workspace_id: str
    sql_warehouse_id: str | None = None


@dataclass(frozen=True, slots=True)
class SnowflakeTarget:
    """A Snowflake environment and supported access mechanisms."""

    environment: SnowflakeEnvironment
    access_modes: frozenset[SnowflakeAccessMode]


@dataclass(frozen=True, slots=True)
class AdlsTarget:
    """A named ADLS Gen2 storage account."""

    environment: AdlsEnvironment
    account_name: str


@dataclass(frozen=True, slots=True)
class OmsTarget:
    """A named production Azure Log Analytics workspace."""

    region: OmsRegion
    workspace_name: str


@dataclass(frozen=True, slots=True)
class InitiativeSmokeTest:
    """External dependencies that one initiative must smoke test."""

    initiative_id: str
    source_paths: tuple[str, ...]
    requires_databricks: bool = False
    requires_snowflake: bool = False
    requires_adls: bool = False


DATABRICKS_RAPREPROD = DatabricksTarget(
    name="pl-databricks-us-rapreprod-01",
    workspace_id="7628572648057993",
)
DATABRICKS_PROD = DatabricksTarget(
    name="pl-databricks-us-prod-01",
    workspace_id="3510128597187204",
    sql_warehouse_id="434de6917eea68b6",
)
DATABRICKS_TARGETS = {
    "data_engineering": DATABRICKS_PROD,
    "ra": DATABRICKS_RAPREPROD,
}

SNOWFLAKE_TARGETS = tuple(
    SnowflakeTarget(
        environment=environment,
        access_modes=frozenset(
            {
                SnowflakeAccessMode.PYTHON_CONNECTOR,
                SnowflakeAccessMode.CORTEX,
            }
        ),
    )
    for environment in SnowflakeEnvironment
)

ADLS_DEV = AdlsTarget(
    environment=AdlsEnvironment.DEV,
    account_name="pladls2usdatamartdev",
)
ADLS_STAGING = AdlsTarget(
    environment=AdlsEnvironment.STAGING,
    account_name="pladls2usdatamartpreprod",
)
ADLS_PROD_US = AdlsTarget(
    environment=AdlsEnvironment.PROD_US,
    account_name="pladls2usdatamartprod",
)
ADLS_PROD_CA = AdlsTarget(
    environment=AdlsEnvironment.PROD_CA,
    account_name="pladls2cacdatamartprod",
)
ADLS_TARGETS = {
    target.environment: target
    for target in (
        ADLS_DEV,
        ADLS_STAGING,
        ADLS_PROD_US,
        ADLS_PROD_CA,
    )
}
ADLS_PREPROD = ADLS_STAGING

OMS_TARGETS = {
    target.region: target
    for target in (
        OmsTarget(OmsRegion.US, "pl-oms-us-primary"),
        OmsTarget(OmsRegion.CA, "pl-oms-ca-primary"),
    )
}

INITIATIVE_SMOKE_TESTS = (
    InitiativeSmokeTest(
        initiative_id="l3_catch_up_trigger",
        source_paths=("dags/precisionlender/dags/l3_trigger_dag_catchup.py",),
        requires_databricks=True,
        requires_adls=True,
    ),
    InitiativeSmokeTest(
        initiative_id="opportunity_guidance_sharing_de_3207",
        source_paths=(
            "de-jobs/src/datamart/jobs/snowflake/evolutions/v1_0_26_de_3207.py",
        ),
        requires_snowflake=True,
    ),
    InitiativeSmokeTest(
        initiative_id="ra_dataeng_metadata_ingestion",
        source_paths=(
            "de-jobs/src/datamart/jobs/ra/data_eng_relationship_metadata/",
            "de-jobs/src/datamart/jobs/ra/data_eng_core_loan_account_metadata/",
            "de-jobs/src/datamart/jobs/ra/data_eng_core_deposit_account_metadata/",
            "de-jobs/src/datamart/jobs/ra/data_eng_core_other_account_metadata/",
        ),
        requires_databricks=True,
        requires_adls=True,
    ),
    InitiativeSmokeTest(
        initiative_id="opportunity_draw_schedules_de_2846_de_3044",
        source_paths=(
            "ds-jobs/src/datascience_jobs/jobs/data/opportunities/"
            "account_level_opportunity_draw_schedule_history.py",
            "ds-jobs/src/datascience_jobs/jobs/data/opportunities/"
            "account_level_opportunity_draw_schedule_snapshot.py",
        ),
        requires_databricks=True,
        requires_snowflake=True,
        requires_adls=True,
    ),
    InitiativeSmokeTest(
        initiative_id="treasury_financial_statement_fields_de_3023_de_3077",
        source_paths=(
            "de-jobs/src/datamart/jobs/ra/treasury_financial_statement_breakdown/",
        ),
        requires_snowflake=True,
        requires_adls=True,
    ),
    InitiativeSmokeTest(
        initiative_id="andi_historical_backfill_de_2953",
        source_paths=("dags/precisionlender/dags/de_2953_backfill.py",),
        requires_databricks=True,
        requires_adls=True,
    ),
)
