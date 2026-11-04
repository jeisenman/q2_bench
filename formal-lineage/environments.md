# Separate validation environments

Each original implementation runs in its own reference environment. Matching
versions across projects does not permit sharing an active environment.
The common formal model and source parser remain Go tooling.

| Environment | Runtime binding | Isolation |
| --- | --- | --- |
| DI Pipelines | Python 3.12.x, Pandas 2.2.3, Spark 4.1.0, from pinned pyproject.toml | Its own RA preproduction compute and private source/work/cache/artifact roots |
| RADAR | Observed Python 3.10.12, Pandas 1.5.3, Spark 3.5.0 / DBR 14.3 | Separate RA preproduction compute and private roots |
| Data Ingress | Native .NET 10; SDK source pin 10.0.100 with latestFeature roll-forward | Separate process, checkout, CLI home, NuGet directories and artifacts |
| Calculation engine C# | Native .NET 10 test runtime; core library targets netstandard2.1 | Separate process and filesystem even when its SDK matches Data Ingress |
| Calculation engine TypeScript | TypeScript 4.9.4; supported Node version unresolved | Separate Node process, checkout, node_modules and npm cache; execution blocked until runtime binding |
| Databricks SDK bridge | Retained uv-managed Python 3.11+ tooling | Separate host tooling environment; never used as the application's Python interpreter |

Data Ingress's pinned repository contains no tracked Python implementation
files. Its calculation project targets net10.0. The Python version difference
here is between DI Pipelines and RADAR. The user explicitly selected separate
reference environments, so retaining legacy RADAR Python 3.10 does not require
upgrading that shared cluster to match host tooling.

## Bindings and preflight

```bash
go run ./cmd/agentbench formal-lineage environments
go run ./cmd/agentbench formal-lineage check-environments \
  --bindings /path/to/provider-observed-bindings.json --output /tmp/compatibility.json
```

The SDK selector `10.0.100+` permits stable 10.0 SDK feature bands starting
at 10.0.100; it does not permit a different major/minor version.

The binding document is an array of `profile_id`, `platform`, `workspace_id`
(for RA), `isolation_id`, `root` and observed `versions`. Supply the complete
set selected for a campaign. Use actual provider compute identities / native
process identities; do not reuse a single Databricks cluster for both Python
profiles, even across different notebooks. Distinct work directories alone
cannot isolate cluster-installed packages or interpreter state.

Preflight rejects wrong platforms/workspaces/versions, missing identities,
unknown profiles, repeated compute/process IDs, duplicate profiles and shared
or nested work roots. It emits private install/cache environment variables.
Bindings are declarations until authenticated provider metadata verifies them;
passing preflight is not proof that environments were created or jobs executed.

Launches must use fresh processes and reviewed environment allowlists, a
private source checkout below each root, and private build/test outputs.
Create required directories before starting tools. Use per-environment
`DOTNET_CLI_HOME`, `NUGET_PACKAGES`, `NUGET_HTTP_CACHE_PATH`, uv/pip caches,
virtual environments and npm caches. Resolve physical paths at launch so
symlink aliases cannot share a native work directory. Never install packages
into another profile's environment. Do not import application Python locally.

RA preproduction remains the location for both dataframe environments.
`radar-264227` is the observed RADAR reference resource. A separate RA resource
matching DI's Python/Pandas/Spark requirements remains unbound. No cluster was
provisioned or upgraded by this change; unresolved whole-job lowering and
native configuration/dependency closure still block full execution.

Environment profiles and source digests are emitted by the CLI. Compare
identical serialized inputs and complete output bags across native runtimes;
each receipt must retain its profile, compute/process ID, observed package
versions, source pins, seeds and output digest. Historical receipts keep their
original environment and scope.
