# Shared formal-lineage scaffold validation

The project separates DI Pipelines, RADAR, Data Ingress and calculation-engine
source adapters while retaining one method contract and the existing CLI/API.
See [project overview](../../../../../formal-lineage/README.md) and
[resource check](../../../../../formal-lineage/resources.md).

- `ra_probe.py`: exact reviewed remote-data SOURCE wrapper; no client data.
- `submission.json`: target, digest, cluster and submitted run identifiers.
- `ra-probe-output.json`: Jobs API parent/child states and actual notebook output.
- `source-catalog-summary.json`: representative pinned files, declaration and
  operation counts, catalog digests and readiness. Full local catalogs live in
  `var/lineage/shared-scaffold-20261103/` and can be regenerated with the shared
  CLI using their recorded repository/commit/path.
- `migration.json`: preserved DI comparison counts; historical observations
  remain in the original boundary/property investigations.

The RA synthetic predicate passed in Pandas and Spark. Its observed Python
3.10.12 is retained in a separate RADAR reference profile under the user's
runtime-isolation instruction. `environment-policy.json` supersedes the
earlier global-version assessment; original probe/verification receipts remain
unchanged. `native-environment-probe.json` records distinct .NET processes and
private roots/caches, using SDK metadata only. No application execution or
whole-job qualification is claimed. New non-DI methods remain non-executable.
Syntax discovery is not all-repository coverage or dataset routing validation.
