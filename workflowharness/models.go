// Package workflowharness executes typed deterministic workflows.
package workflowharness

import (
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// SideEffectPolicy declares whether a stage requires explicit authorization.
type SideEffectPolicy string

const (
	ReadOnly         SideEffectPolicy = "read_only"
	ApprovalRequired SideEffectPolicy = "approval_required"
)

// EventKind identifies bounded workflow lifecycle events.
type EventKind string

const (
	RunStarted     EventKind = "run.started"
	StageStarted   EventKind = "stage.started"
	StageCompleted EventKind = "stage.completed"
	StageFailed    EventKind = "stage.failed"
	RunCompleted   EventKind = "run.completed"
	RunFailed      EventKind = "run.failed"
)

// CapabilityDefinition describes one external workflow capability.
type CapabilityDefinition struct {
	Name             string
	Description      string
	SideEffectPolicy SideEffectPolicy
}

// StageDefinition describes one ordered workflow stage.
type StageDefinition struct {
	Name             string
	Description      string
	Capabilities     []string
	SideEffectPolicy SideEffectPolicy
}

// Definition describes a versioned workflow independently of its runtime.
type Definition struct {
	Name         string
	Description  string
	Version      string
	Stages       []StageDefinition
	Capabilities []CapabilityDefinition
}

// Validate checks stage uniqueness, capability references, and side effects.
func (d Definition) Validate() error {
	for name, value := range map[string]string{
		"workflow name": d.Name, "workflow description": d.Description,
		"workflow version": d.Version,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", name)
		}
	}
	if len(d.Stages) == 0 {
		return fmt.Errorf("workflow %q must define at least one stage", d.Name)
	}
	capabilities := make(map[string]CapabilityDefinition, len(d.Capabilities))
	for _, capability := range d.Capabilities {
		if strings.TrimSpace(capability.Name) == "" ||
			strings.TrimSpace(capability.Description) == "" {
			return fmt.Errorf("capability name and description must not be empty")
		}
		if _, exists := capabilities[capability.Name]; exists {
			return fmt.Errorf("workflow %q contains duplicate capabilities", d.Name)
		}
		capabilities[capability.Name] = capability
	}
	stages := make(map[string]struct{}, len(d.Stages))
	for _, stage := range d.Stages {
		if strings.TrimSpace(stage.Name) == "" || strings.TrimSpace(stage.Description) == "" {
			return fmt.Errorf("stage name and description must not be empty")
		}
		if _, exists := stages[stage.Name]; exists {
			return fmt.Errorf("workflow %q contains duplicate stage names", d.Name)
		}
		stages[stage.Name] = struct{}{}
		seenCapabilities := make(map[string]struct{}, len(stage.Capabilities))
		for _, name := range stage.Capabilities {
			if _, exists := seenCapabilities[name]; exists {
				return fmt.Errorf("stage %q contains duplicate capabilities", stage.Name)
			}
			seenCapabilities[name] = struct{}{}
			capability, exists := capabilities[name]
			if !exists {
				return fmt.Errorf("stage %q references unknown capabilities: %s", stage.Name, name)
			}
			if capability.SideEffectPolicy == ApprovalRequired &&
				stage.SideEffectPolicy != ApprovalRequired {
				return fmt.Errorf(
					"read-only stage %q references approval-required capabilities: %s",
					stage.Name,
					name,
				)
			}
		}
	}
	return nil
}

// Request represents one typed workflow invocation.
type Request[T any] struct {
	Input            T
	CorrelationID    string
	Attributes       domain.Attributes
	AuthorizedStages map[string]struct{}
}

// Validate checks correlation and authorization values.
func (r Request[T]) Validate() error {
	if strings.TrimSpace(r.CorrelationID) == "" {
		return fmt.Errorf("correlation_id must not be empty")
	}
	for name := range r.AuthorizedStages {
		if strings.TrimSpace(name) == "" {
			return fmt.Errorf("authorized stage must not be empty")
		}
	}
	return nil
}

// RunResult returns typed output and verified execution metadata.
type RunResult[T any] struct {
	Output          T
	CorrelationID   string
	CompletedStages []string
	Attributes      domain.Attributes
}

// Event records bounded workflow lifecycle metadata without payloads.
type Event struct {
	Kind            EventKind
	WorkflowName    string
	WorkflowVersion string
	CorrelationID   string
	StageName       string
	ErrorType       string
}
