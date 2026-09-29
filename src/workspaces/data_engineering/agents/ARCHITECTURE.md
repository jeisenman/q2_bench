# Data-engineering agent benchmark coverage

This diagram records the public benchmark case count for each top-level agent
package. MCP tools warn when an invoked agent has fewer than three cases.
Agents with more than three cases are highlighted as thoroughly exercised;
exactly three meets the warning threshold but is shown separately.

```mermaid
flowchart TB
    MCP[MCP execution boundary]

    MCP --> AL[anti-leak<br/>11 cases]
    MCP --> RD[resource-discovery<br/>4 cases]
    MCP --> BB[benchmark-builder<br/>0 cases]
    MCP --> DC[data-creator<br/>0 cases]
    MCP --> DF[data-finder<br/>0 cases]
    MCP --> DIT[data-insight-triage<br/>0 cases]
    MCP --> ETL[etl<br/>0 cases]
    MCP --> KPO[kpo-sizer<br/>0 cases]
    MCP --> OMS[oms-agent<br/>0 cases]
    MCP --> PSE[prod-support-evolution<br/>0 cases]
    MCP --> PU[python-upgrade<br/>4 cases]

    classDef thorough fill:#d7f5df,stroke:#1f7a3d,color:#102a18
    classDef threshold fill:#fff2c7,stroke:#9a6b00,color:#332400
    classDef warning fill:#ffd9d9,stroke:#a12626,color:#3b0d0d

    class AL,PU thorough
    class RD threshold
    class BB,DC,DF,DIT,ETL,KPO,OMS,PSE warning
```

Counts are derived from public `cases.yaml` files beneath
`src/workspaces/data_engineering/benchmarks/`, excluding `deprecated/`. Update
this diagram when cases or top-level agent packages are added or removed.

`production-support` is no longer listed here. It migrated to
`workflows/prod_support/` and is driven by the harness through the
`production-support` skill, so it is not an agent package. Its handoff cases
were deprecated with the in-process orchestrator they scored and remain as
source data under `benchmarks/deprecated/production_support/`.
