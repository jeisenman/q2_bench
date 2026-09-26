# Isolated production-support capability benchmark

`prod-bench` is the focused companion to the end-to-end `prod-support`
benchmark. It exists because a complete production-support run combines
discovery, evidence collection, orchestration, classification, routing, and
two audience-specific renderers. A synthesis omission in that workflow can
hide whether an underlying capability actually works.

The first suite is located at:

```text
src/workspaces/data_engineering/benchmarks/prod_bench/dates/09-26-26/
```

Each evaluation has:

- one named capability;
- one focused case;
- one small synthetic fixture set;
- one judge criterion with weight `1.0`;
- a unique artifact root.

The matrix loader detects the evaluation's `capability` field and builds a
focused prompt from the case's `prompt` and `instructions`. It does not inject
the full production-support report contract for these cases.

Use `prod-bench` while developing or comparing a specific behavior. Run the
existing `prod-support` suite afterward to verify coordination and complete
report synthesis.

See the dated
[`README.md`](../src/workspaces/data_engineering/benchmarks/prod_bench/dates/09-26-26/README.md)
for capability names and commands.
