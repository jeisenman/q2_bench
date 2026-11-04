# RADAR parser scaffold

Parse existing notebook/library Python with the same standard Python grammar
as DI Pipelines. Pandas and PySpark calls map to the common candidate vocabulary
while retaining separate runtime hints. Notebook magic is preserved for review.
ADF pipeline JSON retains each activity, nested activity pointer, dependency
condition text and referenced pipeline. Expressions and physical effects
remain unresolved. See [project.json](project.json) for repository pins.

The initial source path follows `Transform_Loans.py` through transformed loan
datasets and ADF's `transform-calculation-batch` /
`relationship-family-calculation` into Data Ingress engine calls. These are
source references, not an end-to-end executable model.

Validation uses remote-data `platform: ra`, workspace
`7628572648057993` (`pl-databricks-us-rapreprod-01`), existing cluster
`0715-200455-2cdaolnz` (`radar-264227`). It has no registered SQL warehouse.
Use synthetic inputs and intercept output/upload functions before executing
source fragments. Any client-data comparison needs explicit client/window
parameters and a reviewed read-only notebook.

Resource check: all three repository checkouts and source pins are available;
RA credentials resolve to the approved workspace. The synthetic runtime probe
passed (Spark 3.5.0, Pandas 1.5.3, Python 3.10.12). Keep that legacy reference
in a [separate environment](../environments.md) from DI's Python 3.12 / Spark
4.1.0 runtime and the Python 3.11+ host SDK bridge. Separate DI compute remains
unbound; the existing RADAR cluster does not need an upgrade for this plan.
See [resource evidence](../resources.md). Pandas semantics,
SQL/notebook magic execution, remote library versions, dataset contracts,
stateful code and effect interception still need implementation and binding.
No all-notebook or end-to-end correctness claim is made by this scaffold.

See the [source-level contradiction findings](contradictions.md) for isolated
Boolean proofs and their RA preproduction execution evidence.
