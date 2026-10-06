# Production-support workflow

## Purpose

This package provides deterministic production-support domain operations:
operational windows, regional Airflow and cluster checks, evidence
classification, report details, and exact retry selection. Investigation is
read-only; retry execution belongs to an adapter and requires explicit caller
authorization.

## Architecture

[`dates.go`](dates.go) and [`models.go`](models.go) define validated domain
values. [`checkers.go`](checkers.go) performs bounded regional reads.
[`classification.go`](classification.go), [`evidence.go`](evidence.go), and
[`workloads.go`](workloads.go) derive findings. [`report_config.go`](report_config.go)
and [`report_details.go`](report_details.go) prepare deterministic reporting.
[`retry.go`](retry.go) selects and groups exact retry candidates.

The package owns no global mutable state. Airflow and cluster checks fan out
once per selected region and preserve result order. `context.Context` carries
cancellation and W3C-compatible trace context to sources. The invoking
composition root owns the workflow span; source adapters own external-call
child spans. Pure classification and reporting create no spans.

## Dependencies

- Internal packages: package-local immutable models only.
- Injected protocols: `AirflowFailureSource`,
  `RegionalAirflowFailureSource`, and `ClusterHealthSource`.
- External services or SDKs: Airflow and cluster systems through adapters.
- Runtime configuration: explicit regions and operational timestamps.
- Telemetry: caller-owned workflow span and adapter-owned source spans;
  concrete OpenTelemetry SDKs and exporters are external.

## Workflow

1. Resolve and validate the operational window and region scope.
2. Discover Airflow failures and cluster health concurrently by region.
3. Deduplicate and sort exact task failures.
4. Classify bounded evidence and derive workload or cluster findings.
5. Produce audience-safe report details and retry candidates.
6. Parse an explicit follow-up direction and group selected tasks by region,
   DAG, and run for a separately authorized adapter call.

Invalid boundaries, incomplete evidence, unknown retry numbers, and source
failures stop immediately. Investigation has no external side effects. This
package selects retries but does not execute them. Trace context remains active
across each concurrent source call and ends in the invoking composition root.

## Verification

[`prodsupport_test.go`](prodsupport_test.go) and
[`report_details_test.go`](report_details_test.go) cover windows, filters,
classification, workloads, report identity, and retry selection.
[`../../adapters/airflow/airflow_test.go`](../../adapters/airflow/airflow_test.go)
checks exact retry payloads and transient retry behavior. Correlation,
parent-child span, and redaction assertions remain at the composition and
adapter level.

## Change policy

Update this document when workflow order, concurrency, evidence policy,
reporting, retry selection, dependencies, side effects, or telemetry ownership
changes.
