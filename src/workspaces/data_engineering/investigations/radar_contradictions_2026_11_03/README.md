# RADAR impossible-condition evidence

See the [findings](../../../../../formal-lineage/radar/contradictions.md).
This is an existence check for two source-level contradictions, not an
exhaustive audit of every RADAR transform or a complete executable formal model.

Reproduce the immutable source payload, Go predictions and reviewed SOURCE:

```bash
go run ./src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03
```

Generated local artifacts live under
`var/lineage/radar-contradictions-20261103/`: `payload.json`, `prepared.py`,
`wrapped.py`, and the unknown-status source catalogs. The payload retains
full original source bytes at immutable Git pins and verifies their hashes
remotely before selecting definitions. The compressed payload is data, not an
import path or an application module initializer.

`compare.py` is a remote-only notebook template. `prepare.go` is pure Go source
preparation and independent Boolean/output prediction. Never execute the
application Python locally. Use remote-data platform ra and the existing
RADAR reference cluster; do not install packages or invoke source I/O.

`proofs.json` retains the all-eight-state nullness proof and all-string-class
portfolio proof. `submission.json` records the exact wrapped SOURCE digest,
workspace, cluster and Jobs run. `run-output.json` retains successful Jobs API parent/child states and actual
notebook output. `results.json` decodes the original-source observations. All
110 library predictions matched and all eight notebook cases reproduced both
the tautological error and its subsequent erasure.

Original business source is not changed. The library fallback still works
for missing factors; only its intersection arm is impossible. The notebook's
early errors are subsequently cleared, so final-row rejection is not inferred.

The notebook ran on RA preproduction, Python 3.10.12 / Pandas 1.5.3 / Spark
3.5.0. `cases.json` retains complete synthetic helper inputs and Go expectations.
The broader method catalogs remain unknown; only isolated predicates and the
reported output/error fields were validated.
