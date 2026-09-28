"""Compatibility exports for OMS contracts now owned by ``oms_agent``."""

from workspaces.data_engineering.agents.oms_agent import (
    OMS_TABLE,
    OmsJobQuery,
    OmsJobQueryParameters,
    OmsQueryParameterError,
    build_oms_job_query,
)

__all__ = [
    "OMS_TABLE",
    "OmsJobQuery",
    "OmsJobQueryParameters",
    "OmsQueryParameterError",
    "build_oms_job_query",
]
