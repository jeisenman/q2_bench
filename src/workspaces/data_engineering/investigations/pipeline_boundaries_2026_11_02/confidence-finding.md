# Treasury D2P confidence contradiction

At di-pipelines commit `20822fe0d10e812d9858d4ec6d550cce1340cac9`,
`DeliveryToPromiseTreasuryData._run` computes the day difference with
`datediff(FirstRefreshDate, OppCloseDate)`, then sets Confidence at lines 183–189:

```python
F.when((F.col("FirstRefreshMinusCloseDate") < -10)
       & (F.col("FirstRefreshMinusCloseDate") > 120), F.lit("Unlikely"))
 .when(F.col("CoreAccountId").isNull(), F.lit("No Core Account Match Found"))
 .otherwise(F.lit("Likely"))
```

The numeric ranges have an empty intersection. A null day difference makes
the condition UNKNOWN, which also does not select this WHEN. The preceding
comment describes “before OR after” behavior, while the code uses AND.

Databricks executed the original pinned clause on nine synthetic input rows.
The independent Go model matched every output row and the output column names.

| Day difference | Core account | Observed Confidence |
|---:|---|---|
| -11 | Present | Likely |
| -10 | Present | Likely |
| -9 | Present | Likely |
| 0 | Present | Likely |
| 119 | Present | Likely |
| 120 | Present | Likely |
| 121 | Present | Likely |
| NULL | Present | Likely |
| 121 | Missing | No Core Account Match Found |

No “Unlikely” output was observed. The null-date fall-through is a separate
review candidate, not a second established contradiction: its expected label
is not specified. Upstream reachability of every synthetic combination and
whole-job behavior remain unverified. No source business rule was changed.

Parent run `172671842241264`, child run `899164602931602`, Spark 4.1.0.
Reviewed SOURCE SHA256:
`02db001b4b908c125d8a589a5092ce4b81297300c2005eb476f552e5405872b1`.
Original source SHA256:
`ff5b68d64b914c5ed499bfdf29d670c83ea423b1589f3ee3f0f158129a87d0d3`.
See `confidence-diagnostic.json`, `confidence-results.json`, and
`impossible-findings.json`. These observations apply to the pinned revision;
they do not establish what is currently deployed.
