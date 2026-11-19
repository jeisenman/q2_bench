---
name: check
description: Verify browser access and agent connectivity to Azure DevOps, scope-appropriate DE or RA Azure Databricks, Azure CLI login, Airflow, and production OMS. Use for connection preflight or help connecting to the browser or these services.
---

# Check connections

Use one small, authenticated, read-only check for each requested resource. A
general check covers browser access, Azure DevOps, Azure CLI, Airflow, required Databricks
workspaces, and both production OMS workspaces. Use the request and approved
repository configuration to set scope and targets. Mark unused targets `not
required`. For each required target, report `connected`, `blocked`, or `not
checked`, with evidence and the next step if blocked.

Use existing credentials and sessions. Keep secrets out of output. Distinguish
missing tools, network failures, expired authentication, and authorization
failures. Continue independent checks after a failure. Do not retry
automatically or change infrastructure. Follow cloud-only restrictions. A
configured MCP, cached account, target listing, or public/login page does not
prove authenticated access.

## Browser access

Include browser access in a general connection check. A browser-only request
checks this target only. Use supported browser control to discover the requested
browser, bind one relevant existing tab, and read its current page state.
Follow the browser tool's initialization instructions. Do not click controls,
submit forms, or change page content for this check.

Report `connected` only after the page state can be read. Browser or tab
discovery alone proves discovery only. If the tab belongs to another session,
report `blocked` with that reason and ask the user to release the tab or select
an available tab. Do not close tabs, take over another session, or retry
automatically. If no suitable tab or browser tool is available, report the
missing prerequisite.

Record only the browser, minimal target information, and read result. Do not
copy private page content into the report. Browser access does not prove
authenticated access to Azure DevOps, Airflow, or another service; verify each
requested service separately.

## Azure DevOps

Open the verified organization/project in a supported browser and confirm authenticated project content; API or CLI success does not replace this browser check. If browser control is unavailable, report `blocked` and provide the URL for the user to open.

```text
https://dev.azure.com/precisionlender/Data%20Engineering
```

## Azure Databricks (DE and RA)

Check DE production `pl-databricks-us-prod-01` for data-engineering work and RA preproduction `pl-databricks-us-rapreprod-01` for RA investigations, checking both when scope crosses workspaces; discover and verify the host and profile from approved configuration. Run the identity command and report identity access only, using interactive OAuth if needed and supported, without creating or exposing a PAT.

```bash
databricks current-user me --profile <workspace-profile>
```

```bash
databricks auth login --host <verified-workspace-url> --profile <workspace-profile>
```

## Azure CLI

Run `az version`, inspect only projected non-secret context, and verify the intended tenant/subscription plus successful token acquisition; cached `account show` context alone is insufficient. If login is missing or expired, use the verified tenant and let the user complete sign-in/MFA, or link [installation instructions](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) if the CLI is missing.

```bash
az account show --query '{tenant:tenantId,subscription:id,state:state}' --output json
az account get-access-token --resource https://management.azure.com/ --query expiresOn --output tsv
```

## Airflow

Select the requested environment explicitly and check US-01 and CA-02 separately for general production; prefer a bounded `get_dag_status` MCP read for a known DAG, otherwise confirm authenticated DAG or Task Instances content in the browser, reporting API and browser access separately. Configure a missing MCP using `docs/connections.md` and `configurations.yaml.example`, recreate the server, and never trigger, clear, retry, mark successful, pause, or delete Airflow resources.

| Environment | Browser URL |
| --- | --- |
| Alpha | `https://airflow.alpha01.precisionlender.com` |
| Staging | `https://airflow.staging.precisionlender.com` |
| US production | `https://airflow-us01.precisionlender.com` |
| CA production | `https://airflow-ca02.precisionlender.com` |

## Production OMS

Call `query_oms` on either the `remote-data` or standalone OMS MCP separately for `production/us` (`pl-oms-us-primary`) and `production/ca` (`pl-oms-ca-primary`), substituting `ca` in the example; a successful empty result still verifies access. Report each workspace and outcome, and mark a missing tool or query error blocked without substituting shell, browser scraping, direct HTTP, or Azure CLI queries.

```json
{
  "environment": "production",
  "region": "us",
  "kql": "DI_Scheduling_CL | take 1",
  "timespan": "P1D"
}
```

## Official connection references

- [Azure CLI sign-in](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively)
- [Azure CLI installation](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- [Databricks CLI authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/authentication)
- [Databricks current-user](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/current-user-commands)
