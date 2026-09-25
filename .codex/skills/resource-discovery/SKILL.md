---
name: resource-discovery
description: Query the PrecisionLender Resource Discovery API for client names, client GUIDs, environments, database servers, databases, storage, and DataLake resources, and maintain a quick UUID-to-client lookup from those searches. Use when asked to look up client resources.
---

# Resource Discovery

## Local Test-Suite Policy

When working in `di-pipelines`, `di-scheduling`, or `di-pyjobs`, do not run local unit, integration, or full test suites. Use static inspection, targeted non-test checks, and remote or Alpha evidence instead. Run a local test suite only when the user explicitly requests it.

Use this skill to query the internal Resource Discovery API. The maintained quick lookup at `references/client-guuid-lookup.json` is a record of prior API results or explicit user-confirmed fallbacks; it does not replace an API lookup when credentials are available.

## Workflow

1. Clarify the identifier only when needed. Useful identifiers include client UUID, client name, subdomain, resource set, environment, database, storage account, or DataLake account.
2. For a client UUID, call the lookup helper. It queries the API and updates the quick lookup after every search. If the UUID is not already in `references/client-guuid-lookup.json`, the helper must add a JSON entry for it before finishing, even when the API has no unique match:

   ```bash
   python3 .codex/skills/resource-discovery/scripts/lookup_client.py <client-uuid>
   ```

3. If the API has no unique result, use only an existing `user-confirmed` cache entry as a fallback. Otherwise leave the quick lookup entry as unresolved with `source: unresolved`, `api_status`, and `last_checked`. State that the API did not provide a unique match; never infer a client name from a partial UUID, Airflow DAG, environment, or subdomain.

4. For other read-only endpoints, pass the API path and any query parameters:

   ```bash
   python3 .codex/skills/resource-discovery/scripts/resource_discovery_api.py /api/v1/resources --query name=<resource-name>
   ```

5. Summarize only non-secret fields returned by the API. Never print access tokens, client secrets, or raw credential values.
6. If the API returns multiple records, report each one and call out the ambiguity rather than choosing silently.

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
python3 .codex/skills/resource-discovery/scripts/lookup_client.py <client-uuid>
```

The lookup helper writes only non-secret client UUID/name metadata to `references/client-guuid-lookup.json`. To add a user-confirmed fallback when the API does not have the client, use:

```bash
python3 .codex/skills/resource-discovery/scripts/lookup_client.py <client-uuid> \
  --confirm-name '<client name>'
```

Resources:

```bash
python3 .codex/skills/resource-discovery/scripts/resource_discovery_api.py /api/v1/resources
```

## Report Shape

Return a concise answer with:

- `Finding`: the direct API answer.
- `Resource Discovery`: client name, provisioned client ID, subdomain, environment, zone, service, resource set, database, storage, and DataLake fields when present.
- `Ambiguities`: multiple API records, missing records, or the identifier needed to disambiguate.
