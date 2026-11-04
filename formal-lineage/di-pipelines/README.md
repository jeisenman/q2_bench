# DI Pipelines formal lineage

The existing compiler, independent Go evaluator, source inventory, boundary
suite and seeded property generator now belong to
`workflows/formallineage/dipipelines/`. Shared executable types belong to
`workflows/formallineage/model/`; `workflows/formalmethod/` is an API facade.
The structural manifests under `lineage/` remain canonical and separate.

- [Compiler and comparison guide](formal-methods.md)
- [Boundary scenarios](pipeline-boundary-tests.md)
- [Seeded properties](property-pipeline-tests.md)
- [Project pin and validation target](project.json)

Scope remains every job in di-pipelines, with basic copies/dispatch grouped
into the associated transformation unit. Whole-job prediction remains blocked.
Historical Spark 4.1.0 receipts confirm 4,299 isolated comparisons across 801
supported clauses, including 2,403 seeded instances. They do not establish
all-job equivalence or complete dataset distribution.

Historical evidence stays at its original location:

- [Initial formal comparisons](../../src/workspaces/data_engineering/investigations/formal_methods_2026_10_30/)
- [Boundary evidence](../../src/workspaces/data_engineering/investigations/pipeline_boundaries_2026_11_02/)
- [Seeded evidence](../../src/workspaces/data_engineering/investigations/pipeline_properties_2026_11_02/)

New dataframe comparisons target RA preproduction through `platform: ra`.
Prior receipts retain their original DE environment and Spark profile. The
migration changes package ownership, not artifact formats or existing IDs.
