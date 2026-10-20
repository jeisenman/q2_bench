# Connection setup and MCP endpoints

Use this sequence when setting up a local checkout. Keep credentials in
`.env`; `configurations.yaml` contains enablement and environment variable
names only.

1. Copy the templates: `cp .env.example .env` and
   `cp configurations.yaml.example configurations.yaml`.
2. Read the [configuration rules](user-configuration.md). Enable only the
   workspace and environments you need; both are off by default.
3. Configure each connection below, then connect the listed MCP server in
   your harness. `.mcp.json` contains stdio entries and must use your checkout
   path. Compose HTTP endpoints bind to localhost only.

## Airflow

The [configuration template](../configurations.yaml.example) maps Airflow
environments (`alpha`, `staging`, `produs`, `prodca`) to the variable names in
[`.env.example`](../.env.example). Fill in the matching host, user, and
password values. The `airflow` MCP uses stdio. Production support combines
Airflow, Resource Discovery, OMS, and lineage tools; see its [tool reference](../src/workspaces/data_engineering/skills/prod-support/references/mcp-tools.md)
and [workflow procedure](../src/workspaces/data_engineering/skills/prod-support/SKILL.md).

## Resource Discovery

Set `RESOURCE_DISCOVERY_*` values in `.env` using the approved service
configuration. Connect the `resource-discovery` stdio MCP. See the
[Resource Discovery skill](../src/workspaces/data_engineering/skills/resource-discovery/SKILL.md)
for the operations and required inputs.

## Databricks

Set up [RA preproduction or DE production](../SETUP.md#databricks-tokens),
including a separate workspace-scoped PAT for each. Configure enablement in
[`configurations.yaml`](../configurations.yaml.example). Use the
`remote-data` stdio MCP; the [Databricks guide](../src/workspaces/data_engineering/skills/remote-data/references/DATABRICKS.md)
covers target selection, notebook generation, and execution.

## Snowflake and Cortex

Follow [warehouse setup](../SETUP.md#snowflake-and-cortex) and the
[environment and route reference](warehouse-environments.md). The supported
dev connection file is mounted read-only; live calls require an explicit
environment. The HTTP services are `warehouse` and `cortex`.

## MCP endpoints

The stdio servers in `.mcp.json` are `airflow`, `remote-data`, `warehouse`,
`prod-support`, `oms`, and `resource-discovery`. Stdio servers have no network
URL. `lineage` is registered in the [server](../mcpapi/server.go) but is not
listed in `.mcp.json` by default.

| Streamable HTTP server | Local endpoint | Tool reference |
| --- | --- | --- |
| `prod-support` | `http://127.0.0.1:8765/mcp` | [production-support tools](../src/workspaces/data_engineering/skills/prod-support/references/mcp-tools.md) |
| `warehouse` | `http://127.0.0.1:8766/mcp` | [warehouse and Cortex routes](warehouse-environments.md#mcp-routes) |
| `cortex` sidecar | `http://127.0.0.1:8767/mcp` | [Cortex routes](warehouse-environments.md#mcp-routes) |

Recreate the Compose service after configuration changes using the commands in
[SETUP.md](../SETUP.md#restart-after-mcp-changes). A client reconnect does not
reload its process configuration.
