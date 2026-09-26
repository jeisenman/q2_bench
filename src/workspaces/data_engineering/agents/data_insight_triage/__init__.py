"""Public API for the Data Insight Triage agent."""

from workspaces.data_engineering.agents.data_insight_triage.agent import (
    DATA_INSIGHT_TRIAGE_DEFINITION,
    DataInsightTriageAgent,
)

__all__ = ["DATA_INSIGHT_TRIAGE_DEFINITION", "DataInsightTriageAgent"]
