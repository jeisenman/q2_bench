# Data-engineering outbound targets

The data-engineering workspace keeps non-secret infrastructure identifiers in
`adapters.outbound.data_engineering`. Credentials and provider clients belong
at the composition boundary and must implement the narrow probe ports exported
from `ports`.

Configured targets:

- Databricks RA preprod: `pl-databricks-us-rapreprod-01`, workspace
  `7628572648057993`.
- Databricks production: `pl-databricks-us-prod-01`, workspace
  `3510128597187204`, SQL warehouse `434de6917eea68b6`.
- Snowflake: alpha, staging, and US production through either the Python
  connector or Cortex.
- ADLS data mart: `pladls2usdatamartdev` for dev,
  `pladls2usdatamartpreprod` for staging, `pladls2usdatamartprod` for US
  production, and `pladls2cacdatamartprod` for CA production.
- OMS production: `pl-oms-us-primary` and `pl-oms-ca-primary`.

Shared Databricks notebook examples are maintained in the private
[`precisionlender/radar-notebooks` Shared directory](https://github.com/precisionlender/radar-notebooks/tree/master/notebooks/Shared).

The `remote-data-mcp` server lists these targets and builds reviewable,
read-only Databricks source notebooks for Databricks, ADLS, and Snowflake. It
also owns raw OMS query execution. OMS classification remains in the
production-support workflow so the remote-data boundary does not infer
diagnoses.

`INITIATIVE_SMOKE_TESTS` maps each current Luna-discovered data-engineering
initiative to its required platforms. Concrete external tests should inject
approved provider adapters, execute only minimal read-only probes, and skip
with an actionable message when credentials are unavailable.

Reviewed: 2026-09-29.
