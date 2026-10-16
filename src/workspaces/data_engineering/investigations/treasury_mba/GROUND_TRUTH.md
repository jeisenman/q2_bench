# Treasury MBA — Verified Ground Truth

All facts below were verified against the live warehouse on 2026-10-14 via
`sql_execute` on connection `default` (account `Q2E-GTODUSE1`, role
`SF_DEV_DS_READ_ONLY`). Do not re-derive these; do not contradict them.

## Source

`PL_DATA_STUDIO.DERIVED.CORE_TREASURY_ACCOUNTS_MONTHLY`

Latest snapshot is **`VERSION_PARTITION = '2.5'` AND `DATE_PARTITION = '2026-08-31'`**.
The table holds 388 rows total across two versions (`2.3` → 2026-05-31, `2.5` → 2026-08-31).
Always pin both partition columns; an unpinned query mixes versions.

### Snapshot scale (version 2.5)

| Measure | Value |
|---|---|
| Rows | 97 |
| Distinct `RELATIONSHIP_ID` (baskets) | **9** |
| Distinct `TREASURY_SERVICE_NAME` (items) | **11** |
| Distinct `TREASURY_SERVICE_GROUP_NAME` | **0 — column is 100% NULL** |
| Distinct `TOP_LEVEL_PARENT` | 6 |
| Distinct `CORE_ACCOUNT_ID` | 97 (unique per row) |
| Distinct `ACCOUNT_TYPE` | 1 (`Treasury - Cash Management`) |

## The critical finding: the basket matrix is degenerate

`TREASURY_SERVICE_GROUP_NAME` is entirely NULL, so group names must be recovered
by join (below). Once recovered there are only **3 groups**: `DDA`, `LockBox`,
`Wire Transfer` — and **all 3 appear in all 9 baskets**.

**At the service-group grain every support = 1.000, every confidence = 1.000,
and every lift = exactly 1.0.** There is zero variance. Any association-rule
output at this grain is a constant matrix, identical across all five approaches.

At the `TREASURY_SERVICE_NAME` grain there is exactly one bit of variation:

| Service | Baskets containing | Support |
|---|---|---|
| Checks Deposited | 9 | 1.000 |
| Debits | 9 | 1.000 |
| Incoming Domestic | 9 | 1.000 |
| Items Deposited | 9 | 1.000 |
| Monthly Servicing | 9 | 1.000 |
| Outgoing Domestic | 9 | 1.000 |
| Retail Item | 9 | 1.000 |
| Wholesale Deposit | 9 | 1.000 |
| Wholesale Item | 9 | 1.000 |
| Incoming Foreign | 8 | 0.889 |
| Outgoing Foreign | 8 | 0.889 |

Basket sizes: eight baskets contain all 11 services; one basket
(`025d8b3e-…`, *OBX Integrated & Co.*) contains 9, missing **both**
`Incoming Foreign` and `Outgoing Foreign`. Those two services co-occur
perfectly (8/8, Jaccard = 1.0).

Consequences every notebook must state plainly:

- Minimum non-zero support is 1/9 = 0.111; support is quantised to ninths.
- Lift takes only the values **1.0** and **1.125** (= 1/0.889) across the
  entire dataset. Nothing else is attainable.
- No pair can reach significance. Fisher's exact on the single 9-vs-8 split
  cannot produce p < 0.05 at n = 9.
- The only real structure is the perfect `Incoming Foreign` ↔ `Outgoing Foreign`
  couple and the single relationship lacking both.

**Therefore: report metrics, label them as non-significant, and do not narrate
them as business findings.** The deliverable's value is reusable methodology.

## Recovering `TREASURY_SERVICE_GROUP_NAME`

The dimension is `PL_DATA_STUDIO.INTEGRATION_TESTING."TreasuryServices_Prod_7-1-26"`
(quoted identifier — the name is mixed-case and contains hyphens).

Columns: `INSTANCE_PARTITION`, `TREASURY_SERVICE_GROUP_NAME`,
`TREASURY_SERVICE_GROUP_ID`, `TREASURY_SERVICE_NAME`, `TREASURY_SERVICE_CODE`.

**Fan-out warning.** It holds 5,828 rows but only 4,244 distinct
`TREASURY_SERVICE_CODE` across 16 `INSTANCE_PARTITION` values. A naive join on
`TREASURY_SERVICE_CODE` **doubles the fact rows (97 → 194)** and silently
double-counts every revenue figure. Always pre-deduplicate:

```sql
WITH d AS (
  SELECT DISTINCT TREASURY_SERVICE_CODE, TREASURY_SERVICE_GROUP_NAME
  FROM PL_DATA_STUDIO.INTEGRATION_TESTING."TreasuryServices_Prod_7-1-26"
)
```

This table lives in `INTEGRATION_TESTING`, not a production schema. Treat the
group mapping as provisional and say so.

## Measures

- `FTP_NET_REVENUE` and `STRATEGIC_NET_REVENUE` are populated and, in this
  snapshot, **identical to each other row-for-row**. Do not present them as two
  independent signals.
- All `LockBox` services (`Retail Item`, `Wholesale Deposit`, `Wholesale Item`)
  have revenue **0.00** in every basket. Revenue-weighted analysis therefore
  sees only DDA and Wire Transfer.
- `ACTUAL_MONTHLY_UNITS`, `WAIVED_UNITS`, `YEARLY_VOLUME` are **NULL** in this
  snapshot. Do not build on them.

## Environment

Available: `pandas` 2.3.3, `numpy` 1.26.1, `matplotlib` 3.10.6, `scipy` 1.16.2,
`networkx` 3.2.1, `nbformat`, `nbclient`, `snowflake.connector`, `snowflake.snowpark`.

**`seaborn` is installed but broken** (`matplotlib.cm.register_cmap` removed in
matplotlib 3.10) — importing it raises `AttributeError`. **`mlxtend` is not
installed.** Use matplotlib only; hand-roll Apriori. Do not add dependencies.

Role `SF_DEV_DS_READ_ONLY` permits `SELECT` only — no DDL, no writes.
