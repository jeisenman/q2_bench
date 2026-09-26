# prod-bench snapshot 09-26-26

`prod-bench` evaluates one production-support capability at a time. It does
not ask the candidate to produce the complete production-support report unless
the selected capability is one of the two message-formatting cases.

## Capability evaluations

| Capability | Case | Evaluation manifest |
|---|---|---|
| Date and bounded links | `date-window` | `evaluations/date_window.yaml` |
| Failure discovery | `failure-discovery` | `evaluations/failure_discovery.yaml` |
| Log classification | `log-classification` | `evaluations/log_classification.yaml` |
| Prior-run fallback | `prior-run-fallback` | `evaluations/prior_run_fallback.yaml` |
| Spark evidence race | `spark-evidence-race` | `evaluations/spark_evidence_race.yaml` |
| Timeout short circuit | `timeout-short-circuit` | `evaluations/timeout_short_circuit.yaml` |
| Cluster health | `cluster-health` | `evaluations/cluster_health.yaml` |
| Resource routing | `resource-routing` | `evaluations/resource_routing.yaml` |
| Resend specificity | `resend-specificity` | `evaluations/resend_specificity.yaml` |
| Channel filtering | `channel-filtering` | `evaluations/channel_filtering.yaml` |
| Developer message | `developer-message` | `evaluations/developer_message.yaml` |
| Data Internal message | `data-internal-message` | `evaluations/data_internal_message.yaml` |
| Regional consistency | `regional-consistency` | `evaluations/regional_consistency.yaml` |
| Grouped reporting | `grouped-reporting` | `evaluations/grouped_reporting.yaml` |

## Run one capability

For example, run only prior-run fallback:

```bash
uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/prod_bench/dates/09-26-26/evaluations/prior_run_fallback.yaml \
  --cases src/workspaces/data_engineering/benchmarks/prod_bench/dates/09-26-26/cases.yaml \
  --case prior-run-fallback \
  --configuration sol-light-luna-high-workers \
  --execute
```

Replace the evaluation path and case with another row from the table. Every
evaluation writes to its own artifact directory below
`var/benchmark_matrix/prod-bench-09-26-26/`, so capability results do not
overwrite or baseline against one another.

## Design constraints

- Each evaluation declares exactly one `capability`.
- Each evaluation has exactly one rubric criterion with weight `1.0`.
- Public fixtures contain evidence and output contracts, not expected answers.
- Candidate prompts explicitly prohibit solving unrelated capabilities.
- Regional consistency rejects cross-region findings and health contradictions.
- Grouped reporting covers both shared jobs across clients and multiple jobs for one client.
- Resend cases require reviewed Resource Discovery routes rendered as clickable links.
- Data Internal omits CMM and uses no periods.
- The original `prod-support` benchmark remains the end-to-end integration test.
