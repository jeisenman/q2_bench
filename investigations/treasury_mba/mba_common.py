"""Shared primitives for the treasury market-basket investigations.

Loads the pinned snapshot of
``PL_DATA_STUDIO.DERIVED.CORE_TREASURY_ACCOUNTS_MONTHLY`` and exposes the
basket matrix plus association-rule metric primitives.

The loader works both inside a Snowflake notebook (via the active Snowpark
session) and locally (via ``snowflake.connector`` and the named CLI
connection), so the same notebook runs in either place.

See ``GROUND_TRUTH.md`` for verified facts about this data, in particular that
the basket matrix is degenerate: at the service-group grain every lift is
exactly 1.0.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

FACT_TABLE = "PL_DATA_STUDIO.DERIVED.CORE_TREASURY_ACCOUNTS_MONTHLY"
DIM_TABLE = 'PL_DATA_STUDIO.INTEGRATION_TESTING."TreasuryServices_Prod_7-1-26"'

DEFAULT_VERSION_PARTITION = "2.5"
DEFAULT_DATE_PARTITION = "2026-08-31"

BASKET_KEY = "RELATIONSHIP_ID"
ITEM_SERVICE = "TREASURY_SERVICE_NAME"
ITEM_GROUP = "TREASURY_SERVICE_GROUP_NAME"


@dataclass(frozen=True)
class Snapshot:
    """A pinned extract of the treasury fact table.

    Attributes:
        rows: One row per (relationship, service) with group and revenue.
        version_partition: The pinned ``VERSION_PARTITION``.
        date_partition: The pinned ``DATE_PARTITION``.
    """

    rows: pd.DataFrame
    version_partition: str
    date_partition: str

    @property
    def n_baskets(self) -> int:
        """Number of distinct baskets (relationships)."""
        return int(self.rows[BASKET_KEY].nunique())

    def basket_matrix(self, item_col: str = ITEM_SERVICE) -> pd.DataFrame:
        """Return the boolean basket x item incidence matrix.

        Args:
            item_col: Either ``ITEM_SERVICE`` or ``ITEM_GROUP``.

        Returns:
            Boolean DataFrame indexed by basket, columns sorted by item name.
        """
        if item_col not in self.rows.columns:
            raise KeyError(f"unknown item column: {item_col!r}")
        present = self.rows[[BASKET_KEY, item_col]].dropna().drop_duplicates()
        if present.empty:
            raise ValueError(
                f"{item_col!r} yields no non-null values in this snapshot; "
                "see GROUND_TRUTH.md"
            )
        matrix = pd.crosstab(present[BASKET_KEY], present[item_col]) > 0
        return matrix.reindex(sorted(matrix.columns), axis=1)


def _sql(version_partition: str, date_partition: str) -> str:
    """Build the pinned, fan-out-safe extract query."""
    return f"""
WITH dim AS (
    SELECT DISTINCT TREASURY_SERVICE_CODE, TREASURY_SERVICE_GROUP_NAME
    FROM {DIM_TABLE}
)
SELECT DISTINCT
    f.{BASKET_KEY},
    f.RELATIONSHIP_NAME,
    f.TOP_LEVEL_PARENT,
    f.{ITEM_SERVICE},
    f.TREASURY_SERVICE_CODE,
    dim.TREASURY_SERVICE_GROUP_NAME,
    f.FTP_NET_REVENUE,
    f.STRATEGIC_NET_REVENUE
FROM {FACT_TABLE} AS f
LEFT JOIN dim ON f.TREASURY_SERVICE_CODE = dim.TREASURY_SERVICE_CODE
WHERE f.VERSION_PARTITION = '{version_partition}'
  AND f.DATE_PARTITION = '{date_partition}'
"""


def load_snapshot(
    version_partition: str = DEFAULT_VERSION_PARTITION,
    date_partition: str = DEFAULT_DATE_PARTITION,
    connection_name: str = "default",
) -> Snapshot:
    """Load the pinned snapshot, in-warehouse or locally.

    The dimension join is pre-deduplicated; joining it raw doubles the fact
    rows and double-counts revenue (see GROUND_TRUTH.md).

    Args:
        version_partition: ``VERSION_PARTITION`` to pin.
        date_partition: ``DATE_PARTITION`` to pin.
        connection_name: Named CLI connection, used only outside Snowflake.

    Set ``TREASURY_MBA_CACHE`` to a CSV path to read a cached extract instead
    of querying; used for offline validation only.

    Returns:
        The loaded :class:`Snapshot`.

    Raises:
        RuntimeError: If no Snowflake session can be established.
    """
    query = _sql(version_partition, date_partition)
    cache = os.environ.get("TREASURY_MBA_CACHE")
    if cache:
        frame = pd.read_csv(cache)
    else:
        frame = _read_sql(query, connection_name)
    frame.columns = [str(c).upper() for c in frame.columns]
    if frame.empty:
        raise RuntimeError(
            f"snapshot {version_partition}/{date_partition} returned no rows"
        )
    return Snapshot(
        rows=frame,
        version_partition=version_partition,
        date_partition=date_partition,
    )


def _read_sql(query: str, connection_name: str) -> pd.DataFrame:
    """Execute ``query`` using whichever Snowflake entrypoint is available."""
    try:  # in-warehouse: Snowflake Notebooks
        from snowflake.snowpark.context import get_active_session

        return get_active_session().sql(query).to_pandas()
    except Exception:  # noqa: BLE001 - fall back to a local connection
        pass
    try:
        import snowflake.connector

        with snowflake.connector.connect(
            connection_name=connection_name
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetch_pandas_all()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "no Snowflake session: not running in a notebook and the local "
            f"connection {connection_name!r} failed ({exc})"
        ) from exc


def item_support(matrix: pd.DataFrame) -> pd.Series:
    """Fraction of baskets containing each item, descending."""
    return matrix.mean(axis=0).sort_values(ascending=False)


def pair_metrics(matrix: pd.DataFrame, min_support: float = 0.0) -> pd.DataFrame:
    """Compute association metrics for every unordered item pair.

    Reports support, both directional confidences, lift, leverage, conviction,
    Jaccard, and the raw co-occurrence count. Degenerate cases are handled
    explicitly rather than silently: conviction is ``inf`` when confidence is
    1.0, and ``NaN`` when an antecedent never occurs.

    Args:
        matrix: Boolean basket x item matrix.
        min_support: Drop pairs whose joint support falls below this.

    Returns:
        One row per pair, sorted by lift then support, both descending.
    """
    if matrix.empty:
        raise ValueError("basket matrix is empty")
    n = len(matrix)
    values = matrix.to_numpy(dtype=bool)
    items = list(matrix.columns)
    supports = values.mean(axis=0)

    records = []
    for i, j in itertools.combinations(range(len(items)), 2):
        both = int(np.count_nonzero(values[:, i] & values[:, j]))
        s_joint = both / n
        if s_joint < min_support:
            continue
        s_a, s_b = supports[i], supports[j]
        conf_ab = s_joint / s_a if s_a else np.nan
        conf_ba = s_joint / s_b if s_b else np.nan
        lift = s_joint / (s_a * s_b) if s_a and s_b else np.nan
        union = int(np.count_nonzero(values[:, i] | values[:, j]))
        records.append(
            {
                "antecedent": items[i],
                "consequent": items[j],
                "cooccurrence": both,
                "support": s_joint,
                "support_a": s_a,
                "support_b": s_b,
                "confidence_a_to_b": conf_ab,
                "confidence_b_to_a": conf_ba,
                "lift": lift,
                "leverage": s_joint - s_a * s_b,
                "conviction": _conviction(s_b, conf_ab),
                "jaccard": both / union if union else np.nan,
            }
        )
    if not records:
        return pd.DataFrame(
            columns=[
                "antecedent", "consequent", "cooccurrence", "support",
                "support_a", "support_b", "confidence_a_to_b",
                "confidence_b_to_a", "lift", "leverage", "conviction",
                "jaccard",
            ]
        )
    return pd.DataFrame(records).sort_values(
        ["lift", "support"], ascending=False, ignore_index=True
    )


def _conviction(support_consequent: float, confidence: float) -> float:
    """Conviction, with the confidence==1 pole returned as ``inf``."""
    if np.isnan(confidence):
        return np.nan
    denominator = 1.0 - confidence
    if denominator <= 0:
        return np.inf
    return (1.0 - support_consequent) / denominator


def lift_matrix(matrix: pd.DataFrame) -> pd.DataFrame:
    """Square symmetric lift matrix, diagonal set to ``NaN``.

    Args:
        matrix: Boolean basket x item matrix.

    Returns:
        Item x item lift values suitable for a heatmap.
    """
    items = list(matrix.columns)
    values = matrix.to_numpy(dtype=float)
    n = len(matrix)
    supports = values.mean(axis=0)
    joint = (values.T @ values) / n
    denominator = np.outer(supports, supports)
    with np.errstate(divide="ignore", invalid="ignore"):
        lifts = np.divide(joint, denominator)
    np.fill_diagonal(lifts, np.nan)
    return pd.DataFrame(lifts, index=items, columns=items)


def degeneracy_report(matrix: pd.DataFrame) -> dict[str, object]:
    """Summarise how much usable co-occurrence variation exists.

    Returns:
        Keys ``n_baskets``, ``n_items``, ``distinct_baskets``,
        ``universal_items``, ``distinct_lift_values``, ``is_degenerate`` and
        ``verdict``.

    ``is_degenerate`` is True only in the *total* case: fewer than two distinct
    lift values, so no approach can surface any differential structure. It is
    deliberately strict and **False is not a clean bill of health** — two
    distinct lift values is the weakest possible pass. Read
    ``distinct_baskets`` instead: that is the number that bounds what any
    method can learn, and ``verdict`` interprets it in words.
    """
    lifts = lift_matrix(matrix).to_numpy()
    finite = lifts[np.isfinite(lifts)]
    distinct_lifts = sorted({round(float(v), 6) for v in finite})
    signatures = {tuple(row) for row in matrix.to_numpy(dtype=bool)}
    universal = [c for c in matrix.columns if bool(matrix[c].all())]
    return {
        "n_baskets": len(matrix),
        "n_items": matrix.shape[1],
        "distinct_baskets": len(signatures),
        "universal_items": universal,
        "distinct_lift_values": distinct_lifts,
        "is_degenerate": len(distinct_lifts) < 2,
        "verdict": _verdict(len(signatures), len(distinct_lifts)),
    }


def _verdict(distinct_baskets: int, distinct_lifts: int) -> str:
    """Plain-language reading of how much structure is learnable."""
    if distinct_lifts < 2:
        return (
            "fully degenerate: every lift identical, no method can find "
            "structure"
        )
    if distinct_baskets <= 2:
        return (
            f"near-degenerate: only {distinct_baskets} distinct basket "
            "signatures, so any 'pattern' restates a single deviating basket"
        )
    if distinct_baskets < 10:
        return (
            f"severely limited: {distinct_baskets} distinct basket signatures "
            "is far too few for stable association estimates"
        )
    return f"{distinct_baskets} distinct basket signatures"


def min_detectable_support_delta(n_baskets: int) -> float:
    """Smallest resolvable change in support, i.e. one basket.

    Support is quantised to ``1/n_baskets``; at n=9 nothing finer than 0.111
    is observable, which is why small-n rule mining is uninformative.
    """
    if n_baskets < 1:
        raise ValueError("n_baskets must be >= 1")
    return 1.0 / n_baskets
