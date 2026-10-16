# Treasury Services Market Basket Analysis

Five independent analytical approaches to service co-purchase across treasury
customer relationships, built against PL_DATA_STUDIO production.

## Headline finding: the source data cannot support this analysis

Market basket analysis needs many baskets with varying contents. The pinned
snapshot provides **9 baskets**, of which **8 are identical**.

| | |
|---|---|
| Baskets (`RELATIONSHIP_ID`) | 9 |
| Distinct basket signatures | **2** |
| Items (`TREASURY_SERVICE_NAME`) | 11 |
| Items present in *every* basket | 9 |
| Attainable lift values, service grain | **{1.0, 1.125}** |
| Attainable lift values, group grain | **{1.0}** — fully degenerate |

`TREASURY_SERVICE_GROUP_NAME` — the column the original analysis plan keys on —
is **100% NULL** in this table and must be recovered by join. Once recovered it
yields only 3 groups (DDA, LockBox, Wire Transfer), all of which appear in all 9
baskets. At that grain every support, confidence and lift is a constant.

**The only genuine, defensible finding in the dataset** is that
`OBX Integrated & Co.` is the sole relationship lacking `Incoming Foreign` and
`Outgoing Foreign`; the other 8 hold both. Those two services co-occur perfectly
(8/8). That is one observation at n=9 — a lead, not a validated pattern.

Everything else these notebooks compute is **methodology, not insight**. They
are written to be rerun unchanged when basket volume grows, at which point they
will produce real results. Each notebook states its own limits inline.

See `GROUND_TRUTH.md` for the full verified data profile, including the join
fan-out hazard and the NULL/zero measure columns.

## The five approaches

| # | Notebook | Approach | Why it's distinct |
|---|---|---|---|
| 1 | `01_classical_association_rules.ipynb` | Apriori support / confidence / lift, itemsets to size 3 | The textbook baseline from the original plan |
| 2 | `02_significance_and_power.ipynb` | Fisher's exact, BH-FDR, power & required-sample-size curves | Quantifies *how much data would be enough* — the most actionable output here |
| 3 | `03_similarity_and_clustering.ipynb` | Jaccard/cosine/Ochiai/Dice/phi, hierarchical clustering, MDS | Structure discovery without support thresholds |
| 4 | `04_revenue_weighted.ipynb` | Revenue-weighted support, Lorenz/Gini, opportunity sizing | The only approach using the revenue measures — the reason to use PL_DATA_STUDIO |
| 5 | `05_graph_and_whitespace.ipynb` | Co-occurrence graph, centrality, communities, peer-gap whitespace | Whitespace is the one technique that degrades gracefully at n=9 |

Approach 2 is the one to read first: it turns the data-volume problem into a
number. Approach 5's whitespace half is the only one that yields an actionable
output at current volume.

## What each approach actually produced

All five executed end-to-end with zero errors: 145 cells, 21 figures.

| # | Headline result |
|---|---|
| 1 | 231 frequent itemsets and 1,100 directional rules — spanning exactly **two** distinct lift values (1.0, 1.125). Only 38 of 1,100 rules have lift ≠ 1.0 and every one involves a foreign-wire service. At group grain: 12 rules, all metrics exactly 1.0. |
| 2 | **0 of 55 pairs significant**, before or after FDR correction. The perfect 8/8 foreign-wire pair yields Fisher p = 0.1111 — the *smallest p-value its margins can produce*. Detecting lift 1.25 needs **135 baskets** (15x current); lift 1.10 needs **835** (93x). |
| 3 | 54 of 55 pairs have undefined phi (zero variance). Jaccard/cosine/Dice/Sokal–Michener all score **1.000 on information-free universal pairs** while scoring the one real couple *lower* (0.889) — the similarity ranking is actively inverted. MDS effective rank: **1**. |
| 4 | Revenue adds genuine variance where presence has none: Gini **0.655** across services, top-2 services = **72.1%** of $66,566. Sized the one real gap at **$814.56** (peer range $515–$994). Confirmed `FTP_NET_REVENUE == STRATEGIC_NET_REVENUE` row-for-row, and LockBox revenue is $0.00 everywhere. |
| 5 | The co-occurrence graph is **complete** — 55/55 edges, density 1.000, diameter 1. Betweenness identically 0; community detection returns 1 community at modularity 0.000. Whitespace found the only real signal: 2 gap cells in 99. |

The convergent finding across all five, by five different routes: there is one
fact in this dataset, and it is the `OBX Integrated & Co.` foreign-wire gap.

## Layout

```
src/workspaces/data_engineering/investigations/treasury_mba/
├── README.md                             this file
├── GROUND_TRUTH.md                       verified data facts — authoritative
├── mba_common.py                         shared loader + metric primitives
├── 01_classical_association_rules.ipynb
├── 02_significance_and_power.ipynb
├── 03_similarity_and_clustering.ipynb
├── 04_revenue_weighted.ipynb
└── 05_graph_and_whitespace.ipynb
```

`mba_common.py` owns the pinned extract query, the basket matrix, and the
association metric primitives (`pair_metrics`, `lift_matrix`, `item_support`,
`degeneracy_report`). Notebooks import it rather than duplicating logic.

## Data source

`PL_DATA_STUDIO.DERIVED.CORE_TREASURY_ACCOUNTS_MONTHLY`, pinned to
`VERSION_PARTITION = '2.5'` and `DATE_PARTITION = '2026-08-31'`.

Service group names are recovered from
`PL_DATA_STUDIO.INTEGRATION_TESTING."TreasuryServices_Prod_7-1-26"`. Note this
dimension lives in `INTEGRATION_TESTING`, **not** a production schema, so the
group mapping is provisional. It also requires pre-deduplication: it holds 5,828
rows for 4,244 distinct service codes across 16 instance partitions, and a naive
join doubles the fact rows and silently double-counts revenue.

## Running

In Snowflake (recommended — this is where the notebooks are published): open the
notebook from the Workspace. `load_snapshot()` picks up the active Snowpark
session automatically. `mba_common.py` must sit alongside the notebook.

Locally:

```bash
cd src/workspaces/data_engineering/investigations/treasury_mba
python3 -m nbclient 01_classical_association_rules.ipynb --timeout 300
```

Offline, against a cached extract (no warehouse round-trip, no SSO prompt):

```bash
TREASURY_MBA_CACHE=.snapshot_cache.csv python3 -m nbclient <notebook> --timeout 300
```

## Dependencies

`pandas`, `numpy`, `matplotlib`, `scipy`, `networkx`, and either
`snowflake.snowpark` (in-warehouse) or `snowflake.connector` (local).

Two environment constraints the notebooks are written around:

- **`seaborn` is installed but broken** — it imports against
  `matplotlib.cm.register_cmap`, removed in matplotlib 3.10. All plotting is
  matplotlib-only.
- **`mlxtend` is not installed** — Apriori is hand-rolled in notebook 1.

Role `SF_DEV_DS_READ_ONLY` permits `SELECT` only; nothing here writes to the
warehouse.

## What would make this analysis viable

Notebook 2 computes this precisely. In short: the limiting factor is basket
count, not method. Either wait for `CORE_TREASURY_ACCOUNTS_MONTHLY` to
accumulate relationships, or point these notebooks at a higher-volume source.
One candidate was identified during scoping —
`LIGHTHOUSE.SNAPSHOTS.CUSTOMER_ENABLED_TREASURY_FEATURES` carries ~2,073
customer baskets over 272 treasury features — but it measures digital-banking
*feature enablement* rather than PrecisionLender *services purchased*, and
carries no revenue, so it is not a drop-in substitute.
