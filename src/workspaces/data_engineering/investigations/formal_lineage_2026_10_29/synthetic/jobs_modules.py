# Databricks notebook source
"""Exercise original job run entrypoints while capturing every attempted upload."""

from __future__ import annotations


class CaptureUploader:
    """Capture an original job's output before physical serialization."""

    def __init__(self) -> None:
        """Initialize an empty in-memory sink."""
        self.frame, self.calls = None, 0

    def assign_df(self, name: str, frame: Any) -> None:
        """Capture the original job's output frame."""
        self.frame = frame

    def upload(self, **kwargs: Any) -> None:
        """Record an upload attempt without persisting data."""
        self.calls += 1


def _full_job(data: dict) -> dict:
    """Run original D2P.run with genuine metadata and intercepted dataset I/O."""
    global GOLDEN
    mode = data["mode"]
    DERIVED["SparkDatasetDownloader"] = _factory(_full_inputs(mode), mode == "missing")
    capture = CaptureUploader()
    DERIVED["SparkDatasetUploader"] = SimpleNamespace(
        from_runner=lambda *a, **kw: capture
    )
    runner = DERIVED["DeliveryToPromise"]()
    runner.logger = LOGGER
    runner.activity = SimpleNamespace(window_start_date_partition=20261029)
    try:
        runner.run()
        assert capture.calls == 1, (
            "original run must reach exactly one intercepted upload"
        )
        frame = capture.frame.cache() if mode == "golden" else capture.frame
        rows = frame.collect()
    except FixtureExit:
        assert capture.calls == 0, "an early exit must not upload"
        return {"outcome": "exit"}
    if mode == "golden":
        GOLDEN = frame
    first = rows[0] if rows else None
    return dict(
        outcome="rows",
        count=len(rows),
        deposit=first.OppDepositsPromised if first else None,
        core=first.LastCoreBalancePerDepositType if first else None,
        average6=first.AvgBalance6 if first else None,
        owner_region=first.OpportunityOwnerRegion if first else None,
        uploads_intercepted=capture.calls,
        entrypoint="original DeliveryToPromise.run",
    )
