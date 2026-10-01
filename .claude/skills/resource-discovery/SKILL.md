---
name: resource-discovery
description: Query Resource Discovery, local Contx metadata, and allowlisted Azure resource metadata for client names, client GUIDs, environments, databases, storage, DataLake, and cloud resources. Use when asked to look up client resources.
---

# Resource Discovery

## Local Test-Suite Policy

When working in `di-pipelines`, `di-scheduling`, or `di-pyjobs`, do not run local unit, integration, or full test suites. Use static inspection, targeted non-test checks, and remote or Alpha evidence instead. Run a local test suite only when the user explicitly requests it.

Use this skill to query the internal Resource Discovery API. The maintained quick lookup at `references/client-guuid-lookup.json` is a record of prior API results or explicit user-confirmed fallbacks; it does not replace an API lookup when credentials are available.

## Workflow

1. Clarify the identifier only when needed. Useful identifiers include client UUID, client name, subdomain, resource set, environment, database, storage account, or DataLake account.
2. For a client UUID, call the lookup helper. It queries the API and updates the quick lookup after every search. If the UUID is not already in `references/client-guuid-lookup.json`, the helper must add a JSON entry for it before finishing, even when the API has no unique match:

   ```bash
   python3 .claude/skills/resource-discovery/scripts/lookup_client.py <client-uuid>
   ```

3. If the API has no unique result, use only an existing `user-confirmed` cache entry as a fallback. Otherwise leave the quick lookup entry as unresolved with `source: unresolved`, `api_status`, and `last_checked`. State that the API did not provide a unique match; never infer a client name from a partial UUID, Airflow DAG, environment, or subdomain.

4. For other read-only endpoints, pass the API path and any query parameters:

   ```bash
   python3 .claude/skills/resource-discovery/scripts/resource_discovery_api.py /api/v1/resources --query name=<resource-name>
   ```

5. For a question about a client's database, storage, DataLake, or complete
   effective resource set, call `lookup_contx_resources`. Pass the client name
   as written and select `resource_type` from `database`, `storage`,
   `datalake`, or `all`. Use `resource_kind` only when the caller requests one
   exact Contx datastore kind. The tool resolves the name to one Resource
   Discovery UUID. When Resource Discovery has no exact canonical-name match,
   it may use one exact normalized Contx client-group name to identify the
   partition UUID. It then applies client-group precedence with shared-group
   fallback for each resource kind.
6. Summarize only non-secret fields returned by the API or Contx capability.
   Never print access tokens, client secrets, secret references, users, or raw
   credential values.
7. If Resource Discovery returns multiple client UUIDs, report the ambiguity.
   Do not query Contx until the client identity is unique.
8. For Azure resource inventory, call `lookup_azure_resources` with one target:
   - `ra_preprod` uses PrecisionLender PreProd
     `cde221ff-e7f4-4d39-be20-6f9d532cab60`.
   - `data_engineering` uses PrecisionLender DataScience
     `b7b3f313-bcc8-4754-aa71-a8c9a910841c`.
   - `production` covers production RA and Data Engineering resources in
     PrecisionLender Production
     `71aa0ec0-8411-43a2-9908-ddd2add764eb`.
9. When the Azure capability returns `login_required` or
   `subscription_access_required`, give the returned message and command to the
   user and wait for them to complete `az login` before retrying. The capability
   passes the subscription on every resource command and does not depend on the
   globally active subscription.

When resolving multiple client UUIDs for one production-support run, use the
Resource Discovery batch capability once for the complete mapping. Do not loop
single-client lookups or run `format_client.py` per UUID; the caller should use
the structured batch results for all report labels.

Never write client secrets to tracked repository files, command history snippets, logs, or final answers. Keep local values in ignored `.env` under `# resource discovery`, or supply them through the current shell session.

## Internal API

The Resource Discovery API uses Azure AD client credentials. Use `scripts/resource_discovery_api.py` for token acquisition and read-only GET requests. The script reads ignored `.env` by default and accepts these environment variables:

- `RESOURCE_DISCOVERY_CLIENT_ID` - required.
- `RESOURCE_DISCOVERY_CLIENT_SECRET` - required.
- `RESOURCE_DISCOVERY_TENANT_ID` - required.
- `RESOURCE_DISCOVERY_SCOPE` - required.
- `RESOURCE_DISCOVERY_BASE_URL` - required.

## Common API Calls

Client by provisioned PrecisionLender client UUID:

```bash
python3 .claude/skills/resource-discovery/scripts/lookup_client.py <client-uuid>
```

The lookup helper writes only non-secret client UUID/name metadata to `references/client-guuid-lookup.json`. To add a user-confirmed fallback when the API does not have the client, use:

```bash
python3 .claude/skills/resource-discovery/scripts/lookup_client.py <client-uuid> \
  --confirm-name '<client name>'
```

Resources:

```bash
python3 .claude/skills/resource-discovery/scripts/resource_discovery_api.py /api/v1/resources
```

Client resources from the configured Contx checkout:

```text
lookup_contx_resources(
  client_name="Bank United",
  resource_kind="PrecisionLenderSqlServer",
  environment="production",
)
```

Azure resources in RA preprod:

```text
lookup_azure_resources(
  target="ra_preprod",
  resource_group="PL-GROUP-US-DIPIPELINE-PREPROD",
)
```

## Report Shape

Return a concise answer with:

- `Finding`: the direct API answer.
- `Resource Discovery`: client name and provisioned client ID.
- `Contx`: selected group, resource name and kind, environment, zone, database,
  database server, storage, DataLake, region, and resource group when present.
- `Azure`: target, subscription name and ID, command, result count, resource
  name, type, group, location, and ID. If login is required, return the exact
  message and command before any resource result.
- `Ambiguities`: multiple API records, missing records, or the identifier needed to disambiguate.
