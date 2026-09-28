"""Evidence-qualified Classification Agent."""

from domain import AgentDefinition
from workspaces.data_engineering.agents.production_support.classification import (
    classify_log,
)
from workspaces.data_engineering.agents.production_support.instruction_loader import (
    load_instruction,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    EvidenceSource,
    FailureDiagnosis,
)
from workspaces.data_engineering.agents.production_support.tools import (
    CLASSIFY_FAILURE,
    MAP_DV_TARGETS,
)

CLASSIFICATION_AGENT_DEFINITION = AgentDefinition(
    name="ClassificationAgent",
    description="Short-circuit exact failure evidence and map proven DV targets.",
    instructions=load_instruction("classification_agent"),
    tools=(CLASSIFY_FAILURE, MAP_DV_TARGETS),
    version="1",
)


class ClassificationAgent:
    """Classify exact evidence without performing production mutations."""

    definition = CLASSIFICATION_AGENT_DEFINITION

    def classify(
        self,
        failure: AirflowFailure,
        log: str,
        source: EvidenceSource,
    ) -> FailureDiagnosis:
        """Return one evidence-qualified diagnosis."""
        return classify_log(failure, log, source=source)
