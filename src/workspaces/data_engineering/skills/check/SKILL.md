---
name: check
description: Verify browser access and agent connectivity to Azure DevOps, scope-appropriate DE or RA Azure Databricks, Azure CLI login, and Airflow. Use for connection preflight or help connecting to the browser or these services.
---

# Check connections

Use small, authenticated, read-only checks. Check only the requested service.
For a general check, cover browser access, Azure DevOps, Azure CLI, Airflow, and each required
Databricks workspace.

Use the request and repository to set scope. For `di-pipelines` or DE pipeline
work, prioritize DE Databricks. Use RA for RA investigations. Check both when
the task spans both workspaces or the user requests both. Mark unused
workspaces `not required`. Resolve environment, region, tenant, subscription,
and workspace from the request and approved repository configuration. Do not
guess a missing target.

For each required target, make one bounded check. Report `connected`,
`blocked`, or `not checked`, the exact target, observed evidence, and the next
step if blocked. Continue independent checks after a failure. Do not retry
automatically. Distinguish DNS or network errors, missing tools, expired
authentication, and authorization failures. A configured MCP, target listing,
cached account, login page, or public landing page does not prove authenticated
access.

Use existing credentials and sessions. Never include tokens, passwords,
cookies, authorization headers, or credential files in tool output or reports.
Do not change infrastructure, trigger builds or DAGs, start clusters, submit
notebooks, or install dependencies for a connectivity check. The user must
complete interactive SSO/MFA. Leave the login ready and state the required
step. Follow active cloud-only restrictions. If they prohibit browser control,
report the required browser check as blocked.

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

## Azure DevOps through a browser

1. Use supported browser-tab control, reusing an authenticated tab where
   possible. Open the organization/project URL from the repository remote or
   approved setup documentation. The Q2 DE organization is
   `https://dev.azure.com/precisionlender`; the project is `Data Engineering`.
2. If needed, select the work account and let the user complete Microsoft
   sign-in and MFA. For denied access, request membership in the exact
   organization/project; an Azure CLI login cannot establish browser access.
3. Open a read-only project resource such as Repos or the Pipelines list.
   Confirm the organization, project, and authenticated resource content in
   the rendered page. Record the URL and what loaded. A CLI/API success does
   not replace this browser check. If browser control is unavailable, mark
   this check blocked and give the URL for the user to open.

## Azure Databricks: DE and RA

Discover approved workspace hosts from repository setup, configured CLI
profiles, or `remote-data` MCP `list_remote_data_targets`. Discovery identifies
targets only; follow it with an authenticated workspace request.

| Scope | Expected workspace | Host discovery |
| --- | --- | --- |
| DE production | `pl-databricks-us-prod-01` | Approved `DE_DATABRICKS_HOST` or Azure portal workspace URL |
| RA preproduction | `pl-databricks-us-rapreprod-01` | Approved `RA_DATABRICKS_HOST`; known URL is `https://adb-7628572648057993.13.azuredatabricks.net` |

Confirm these defaults against current configuration. Keep separate
workspace-scoped profiles/credentials. With an existing approved Databricks
CLI profile, run:

```bash
databricks current-user me --profile <workspace-profile>
```

Confirm that the profile's host is the intended workspace and retain only a
minimal identity/result summary. If no profile exists and interactive OAuth
is supported by the workspace, connect with:

```bash
databricks auth login --host <verified-workspace-url> --profile <workspace-profile>
```

Let the user complete sign-in, then run the read-only identity check. An
existing typed connector may instead make an equivalent authenticated
workspace identity request. If CLI/API identity checks are unavailable, open
the verified workspace URL with supported browser control and confirm signed-in
workspace content, reporting browser-only access. Do not claim API access from
a browser session or compute/data permissions from an identity check.

For qtwo_bench's PAT-backed `remote-data` connector, follow its `SETUP.md`:
configure the matching `DE_DATABRICKS_HOST` / `DE_DATABRICKS_TOKEN` or
`RA_DATABRICKS_HOST` / `RA_DATABRICKS_TOKEN` securely. Enable only the required
workspace/environment and recreate the connector after configuration changes.
Do not create or expose a PAT as part of this preflight.

## Azure CLI login

Use `az version` to check availability, then inspect only non-secret context:

```bash
az account show --query '{tenant:tenantId,subscription:id,state:state}' --output json
az account get-access-token --resource https://management.azure.com/ --query expiresOn --output tsv
```

Verify the intended tenant/subscription and successful token acquisition;
`account show` alone is cached context. Never run token acquisition without
the output projection above. This proves CLI authentication, not access to
every Azure resource, DevOps, or Databricks.

If login is missing or expired, run `az login --tenant <verified-tenant-id>`
and let the user complete sign-in/MFA. Use `--use-device-code` when normal
browser login is unavailable; the user completes that flow. Select the
intended subscription with `az account set --subscription <verified-id>`
only when needed for the task, then repeat the check after sign-in. If `az`
is absent, report the missing CLI and its official installation instructions.

## Airflow

Select the environment explicitly; for a general production check with no
regional scope, verify US-01 and CA-02 separately.

| Environment | Browser URL |
| --- | --- |
| Alpha | `https://airflow.alpha01.precisionlender.com` |
| Staging | `https://airflow.staging.precisionlender.com` |
| US production | `https://airflow-us01.precisionlender.com` |
| CA production | `https://airflow-ca02.precisionlender.com` |

Prefer the connected Airflow MCP for a bounded authenticated read, such as
`get_dag_status` for a known exact DAG in the selected environment. Inspect
the live tool schema for required arguments. If no DAG is known or no typed
read tool is available, use supported browser control to open the selected
Airflow UI and confirm the authenticated DAG or Task Instances list loads.
Report whether API or browser access was verified; they use different sessions.

To connect the qtwo_bench Airflow MCP, follow `docs/connections.md` and
`configurations.yaml.example`: configure the selected environment's host/user/
password variables securely, enable that environment, and recreate the server.
Never print `.env`. For browser access, use the existing session or let the
user complete the login screen. Do not click Trigger, Clear, Retry, Mark
Success, pause, or delete. This is connectivity verification, not a production
failure audit or remediation run.

## Official connection references

- [Azure CLI sign-in](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively)
- [Azure CLI installation](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- [Databricks CLI authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/authentication)
- [Databricks current-user](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/current-user-commands)
