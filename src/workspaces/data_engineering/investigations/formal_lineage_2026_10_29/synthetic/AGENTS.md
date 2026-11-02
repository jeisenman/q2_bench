# Synthetic D2P investigation

This directory holds bounded synthetic fixtures and Databricks-only notebook
source for the source-pinned standard DeliveryToPromise reporting path.

- `cases.json` contains concrete synthetic records and literal expected effects.
- `golden-report.json` is the independent complete 50-column reporting oracle.
- `prepare/main.go` verifies pinned Git source hashes and packages fixtures,
  sources and notebook cells into a generated notebook outside the source checkout.
- `bootstrap.py` compiles explicitly selected AST definitions with application
  imports omitted. It never imports or runs application modules globally.
- `stages.py`, `stages_upstream.py`, `jobs.py` and `runner.py` execute original functions with synthetic
  frames and intercepted downloader, uploader, ADLS, path and clock dependencies.
- `module_environment.py` loads an import closure from three exact Git commits,
  checks the 11 selected modules against the source receipt, and installs only
  fixed import dependencies into a per-run temporary directory.
- `bootstrap_modules.py` retains original modules/classes and source metadata,
  supplies isolated runner context, and patches dataset acquisition and sinks.
  It preserves source date/version selectors and normalizes empty Pandas reads
  to None as the original downloader does.
- `jobs_modules.py` invokes the original D2P `run` entrypoint and asserts upload
  interception. `history_modules.py` replaces predicate probes with original
  History account construction using source-schema-derived synthetic records.
  Its default intercepts the account union, calls the original union on three
  identity columns, and stops before remaining History formatting. Full History
  output is an optional troubleshooting mode, not the default validation claim.
- `prepare/imports.go` computes a conservative import closure without rewriting
  application source. Unknown dynamic imports must fail during remote execution.
  `--stages` selects troubleshooting subsets without changing expected values.

Python execution belongs in Databricks. Local preparation uses Go only.
The AST-mode notebook must not read client data, install application dependencies,
write data to storage, or call application upload methods. Full-module mode may
load pinned package source and explicitly versioned import dependencies into a
per-run temporary driver directory, without cluster-library installation. It
must patch downloads and uploads before invoking jobs and retain import hashes.
Submit reviewed generated
SOURCE through the existing remote-data MCP to an approved existing cluster.
Fetch output through the Databricks Jobs API and inspect the embedded suite
status; Databricks lifecycle SUCCESS does not itself mean assertions passed.

Keep each source file under 400 lines. Coverage applies to the named functions
and cases, not all upstream job behavior or all possible input data.
