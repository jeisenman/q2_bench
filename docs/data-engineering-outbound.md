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
- ADLS preprod data mart: `pladls2usdatamartpreprod`.

Shared Databricks notebook examples are maintained in the private
[`precisionlender/radar-notebooks` Shared directory](https://github.com/precisionlender/radar-notebooks/tree/master/notebooks/Shared).

`INITIATIVE_SMOKE_TESTS` maps each current Luna-discovered data-engineering
initiative to its required platforms. Concrete external tests should inject
approved provider adapters, execute only minimal read-only probes, and skip
with an actionable message when credentials are unavailable.

Reviewed: 2026-09-25.
