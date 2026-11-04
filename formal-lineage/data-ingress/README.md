# Data Ingress parser scaffold

Existing `pl-dataingress` C# and the application engine service wrappers feed
Tree-sitter C# and the shared method/source catalog. The application boundary
is restricted to `PrecisionLender.Common.Engine.Proxy/ServiceWrappers/`.
See [project.json](project.json) for exact source pins.

The calculation path begins at `EngineWrapper/EngineCalls.cs`, delegates through
`RAEngineServiceWrapper.cs`, then reaches the calculation engine's RA services
and Standard engines. Lexical calls are retained as unbound dependencies; no
C# overload, interface, reflection or configuration dispatch is guessed.

Resources verified: both repositories, the ingress client `Schema.xml`, and
local .NET SDKs 9.0/10.0. Parsing requires no restore and does not execute source.
Runtime equivalence needs native .NET fixtures with transport/database effects
replaced by bounded test interfaces. RA preproduction remains the Pandas/Spark
validation target; C# code is not treated as a Spark program.

Current readiness is unknown with no executable steps. Required work includes
type-aware binding, DTO/schema contracts, nullable/decimal/exception semantics,
configuration and method resolution, data-effect modeling and native receipts.

The pinned calculation project targets net10.0; global.json selects SDK
10.0.100 with latestFeature roll-forward. No tracked Python implementation
files were found at this source pin. Use the dedicated Data Ingress .NET
process and private dependency directories in the
[environment policy](../environments.md), independently of the engine's .NET
process even when both resolve the same SDK version.
