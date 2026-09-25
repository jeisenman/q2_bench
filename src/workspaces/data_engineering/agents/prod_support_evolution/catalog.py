"""Historical prod-support prompt catalog derived from Git."""

from datetime import date

from workspaces.data_engineering.agents.prod_support_evolution.models import (
    PromptLesson,
    PromptVersion,
)

SOURCE_PATH = ".codex/skills/prod-support/SKILL.md"


def prompt_versions() -> tuple[PromptVersion, ...]:
    """Return prompt revisions in chronological order."""
    return (
        PromptVersion(
            version="v0",
            commit="c11a9a7e73abaf496520594af0e6e50258f4d069",
            committed_on=date(2026, 8, 4),
            title="First prod-support agent prompt",
            source_path=SOURCE_PATH,
            summary=(
                "Introduced discovery, EventBus and high-quality triage, client "
                "mapping, response formatting, and a reflection mechanism."
            ),
            lessons=(
                PromptLesson(
                    weakness="The workflow list ended with an empty step.",
                    improvement=(
                        "Define the full ordered workflow: discovery, identity "
                        "resolution, triage, and summary."
                    ),
                    evidence="Initial text contained a bare list item after Discovery.",
                ),
                PromptLesson(
                    weakness="EventBus instructions appeared twice.",
                    improvement="Remove duplicated policy and keep one canonical rule.",
                    evidence="The initial prompt repeated the complete section.",
                ),
                PromptLesson(
                    weakness="Safety depended on scattered negative instructions.",
                    improvement=(
                        "Add explicit mutation boundaries and approval checkpoints."
                    ),
                    evidence="Retries and resends lacked a unified safety contract.",
                ),
            ),
        ),
        PromptVersion(
            version="v1",
            commit="c301d181c5c39a8e7311f98d668f72b437d40cf0",
            committed_on=date(2026, 8, 7),
            title="Identity and recurrence hardening",
            source_path=SOURCE_PATH,
            summary=(
                "Made client identity resolution mandatory, added fail-closed "
                "behavior, clarified reporting, and required historical checks."
            ),
            lessons=(
                PromptLesson(
                    weakness="Client names could be inferred or resolved too late.",
                    improvement="Resolve every UUID authoritatively before reporting.",
                    evidence="Added Resource Discovery as a required workflow stage.",
                ),
                PromptLesson(
                    weakness="Recurring D2P failures could be silently ignored.",
                    improvement="Check prior history before labeling or omitting them.",
                    evidence="Added a 30-day D2P and subscriber recurrence policy.",
                ),
            ),
        ),
        PromptVersion(
            version="v2",
            commit="dfb7cb6fdbb8bce82d2a34b03c9a9120e44d2e88",
            committed_on=date(2026, 8, 29),
            title="Operational orchestration",
            source_path=SOURCE_PATH,
            summary=(
                "Expanded orchestration and supporting scripts while refining the "
                "agent interface and high-quality triage behavior."
            ),
            lessons=(
                PromptLesson(
                    weakness="A monolithic prompt mixed policy and implementation.",
                    improvement="Move deterministic operations into scripts and tools.",
                    evidence=(
                        "The commit changed both prompt and triage implementation."
                    ),
                ),
                PromptLesson(
                    weakness="The agent interface understated parallel investigation.",
                    improvement="Make independent failure investigation explicit.",
                    evidence=(
                        "The OpenAI interface description changed to parallel triage."
                    ),
                ),
            ),
        ),
        PromptVersion(
            version="v3",
            commit="working-tree-2026-09-25",
            committed_on=date(2026, 9, 25),
            title="Evidence contracts and benchmark feedback",
            source_path=SOURCE_PATH,
            summary=(
                "Separates discovery, exact logs, OMS fallback, classifications, "
                "reporting, retries, and investigation contracts."
            ),
            lessons=(
                PromptLesson(
                    weakness="Exit -9 could be mislabeled as confirmed OOM.",
                    improvement=(
                        "Require corroborating memory evidence for probable OOM."
                    ),
                    evidence="Classification now distinguishes unknown termination.",
                ),
                PromptLesson(
                    weakness="Long-running failures could be missed by start time.",
                    improvement="Discover failures using end_date_gte.",
                    evidence=(
                        "The operational window is now defined by failure end time."
                    ),
                ),
                PromptLesson(
                    weakness="Large logs could overwhelm agent evidence.",
                    improvement="Require concise, source-qualified evidence records.",
                    evidence=(
                        "The 2026-09-24 benchmark exposed oversized evidence output."
                    ),
                ),
            ),
        ),
    )
