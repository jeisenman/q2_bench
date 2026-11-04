# Resource check — 2026-11-03

| Resource | Confirmed state |
| --- | --- |
| DI Pipelines, RADAR notebooks/libraries/ADF | Local Git source pins available |
| Data Ingress + application engine wrappers | Local Git source pins and ingress client Schema.xml available |
| Calculation engine | C#/TypeScript implementations, manifests, locks and test vectors available |
| Standard source parsers | Pinned Tree-sitter Python, C#, TypeScript/TSX bindings; local Go tests pass |
| RA preproduction | Remote-data allowlist and authenticated workspace check both resolve workspace 7628572648057993 |
| RA existing cluster | radar-264227 / 0715-200455-2cdaolnz; synthetic probe completed successfully |
| RA observed runtime | Python 3.10.12, Pandas 1.5.3, Spark 3.5.0; retained as the separate RADAR reference |
| Separate DI RA runtime | Not yet bound; DI source requires Python 3.12.x, Pandas 2.2.3, Spark 4.1.0; all seven observed cluster declarations use DBR 14.3 |
| Native .NET | SDKs 9.0.313 and 10.0.103 available; no engine restore/test claimed |
| NuGet closure | Unknown; CI uses Azure Artifacts, local sources currently public NuGet only |
| Engine test configuration | Actual Configurations/Configurations.json absent; sample exists |

Source pins live in each project.json and are emitted by
`agentbench formal-lineage projects`. Existing framework/library imports,
configuration, complete dataset contracts and effect interception still need
binding before complete job execution.

The [RA probe receipt](../src/workspaces/data_engineering/investigations/shared_formal_lineage_2026_11_03/ra-probe-output.json)
contains the Jobs API child output; lifecycle success alone was not used as
proof. It confirms connectivity and one synthetic predicate in both runtimes.
The observed RADAR reference remains separate from the Python 3.11+ host
SDK bridge and DI's Python 3.12 environment. The probe does not prove a full
source transformation or transfer Spark 4.1.0 passes to Spark 3.5.0.

The [environment policy](environments.md) now separates reference runtimes
under the user's runtime-isolation instruction. Bind separate DI-compatible RA
compute, the required native engine test configuration, and private package
feed access if restore needs it. No shared cluster runtime was changed and no
production/client data was read.
