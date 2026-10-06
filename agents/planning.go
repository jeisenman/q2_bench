package agents

import (
	"context"
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// WorkflowStep describes one ordered, externally visible planning step.
type WorkflowStep struct {
	Name    string
	Outcome string
}

// Validate rejects incomplete workflow steps.
func (s WorkflowStep) Validate() error {
	if strings.TrimSpace(s.Name) == "" {
		return fmt.Errorf("step name must not be empty")
	}
	if strings.TrimSpace(s.Outcome) == "" {
		return fmt.Errorf("step outcome must not be empty")
	}
	return nil
}

// PlanningAgent renders a stable execution plan without external systems.
type PlanningAgent struct {
	definition domain.AgentDefinition
	steps      []WorkflowStep
}

// NewPlanningAgent validates and constructs an immutable planning agent.
func NewPlanningAgent(
	definition domain.AgentDefinition,
	steps []WorkflowStep,
) (*PlanningAgent, error) {
	if err := definition.Validate(); err != nil {
		return nil, err
	}
	if len(steps) == 0 {
		return nil, fmt.Errorf("steps must not be empty")
	}
	copied := append([]WorkflowStep(nil), steps...)
	for _, step := range copied {
		if err := step.Validate(); err != nil {
			return nil, err
		}
	}
	return &PlanningAgent{definition: definition, steps: copied}, nil
}

// Definition returns immutable agent metadata.
func (a *PlanningAgent) Definition() domain.AgentDefinition {
	definition := a.definition
	definition.Tools = append([]domain.ToolDefinition(nil), definition.Tools...)
	return definition
}

// Run returns the deterministic plan for a validated request.
func (a *PlanningAgent) Run(
	_ context.Context,
	request domain.AgentRequest,
) (domain.AgentResult, error) {
	if err := request.Validate(); err != nil {
		return domain.AgentResult{}, err
	}
	var rendered strings.Builder
	rendered.WriteString("Objective: ")
	rendered.WriteString(request.Prompt)
	rendered.WriteString("\nPlan:\n")
	for index, step := range a.steps {
		fmt.Fprintf(&rendered, "%d. %s: %s", index+1, step.Name, step.Outcome)
		if index < len(a.steps)-1 {
			rendered.WriteByte('\n')
		}
	}
	toolCalls := make([]string, len(a.definition.Tools))
	for index, tool := range a.definition.Tools {
		toolCalls[index] = tool.Name
	}
	return domain.AgentResult{
		Output: rendered.String(), CorrelationID: request.CorrelationID,
		ToolCalls: toolCalls,
		Attributes: domain.Attributes{
			{Name: "agent_version", Value: version(a.definition)},
			{Name: "execution_mode", Value: "plan_only"},
			{Name: "step_count", Value: len(a.steps)},
		},
	}, nil
}

func version(definition domain.AgentDefinition) string {
	if definition.Version == "" {
		return "1"
	}
	return definition.Version
}
