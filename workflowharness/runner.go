package workflowharness

import (
	"context"
	"fmt"
	"reflect"
)

// Recorder persists bounded workflow lifecycle events.
type Recorder interface {
	Record(context.Context, Event) error
}

// ExecutionContext runs declared stages with policy enforcement.
type ExecutionContext interface {
	RunStage(context.Context, string, func(context.Context) (any, error)) (any, error)
}

// Workflow exposes metadata and executes a typed request.
type Workflow[Input, Output any] interface {
	Definition() Definition
	Execute(context.Context, Request[Input], ExecutionContext) (Output, error)
}

// ContractError indicates an implementation violated its workflow definition.
type ContractError struct{ Message string }

func (e *ContractError) Error() string { return e.Message }

// AuthorizationError indicates a mutating stage was not authorized.
type AuthorizationError struct{ Stage string }

func (e *AuthorizationError) Error() string {
	return fmt.Sprintf("workflow stage %q requires explicit authorization", e.Stage)
}

type nullRecorder struct{}

func (nullRecorder) Record(context.Context, Event) error { return nil }

// InMemoryRecorder retains lifecycle events for tests and local inspection.
type InMemoryRecorder struct {
	Events []Event
}

// Record appends one event.
func (r *InMemoryRecorder) Record(_ context.Context, event Event) error {
	r.Events = append(r.Events, event)
	return nil
}

// Runner validates workflow policy and externally visible stage execution.
type Runner struct {
	Recorder Recorder
}

// Run executes a workflow and returns verified output metadata.
func Run[Input, Output any](
	ctx context.Context,
	runner Runner,
	workflow Workflow[Input, Output],
	request Request[Input],
) (RunResult[Output], error) {
	var zero RunResult[Output]
	if err := request.Validate(); err != nil {
		return zero, err
	}
	definition := workflow.Definition()
	if err := definition.Validate(); err != nil {
		return zero, err
	}
	if err := validateAuthorizations(definition, request.AuthorizedStages); err != nil {
		return zero, err
	}
	recorder := runner.Recorder
	if recorder == nil {
		recorder = nullRecorder{}
	}
	execution := &executionContext{
		definition: definition, correlationID: request.CorrelationID,
		authorized: request.AuthorizedStages, recorder: recorder,
	}
	if err := execution.record(ctx, RunStarted, "", ""); err != nil {
		return zero, err
	}
	output, err := workflow.Execute(ctx, request, execution)
	if err != nil {
		_ = execution.record(ctx, RunFailed, "", errorType(err))
		return zero, err
	}
	if len(execution.completed) == 0 {
		err = &ContractError{Message: fmt.Sprintf(
			"workflow %q completed without running a stage",
			definition.Name,
		)}
		_ = execution.record(ctx, RunFailed, "", errorType(err))
		return zero, err
	}
	if err := execution.record(ctx, RunCompleted, "", ""); err != nil {
		return zero, err
	}
	return RunResult[Output]{
		Output: output, CorrelationID: request.CorrelationID,
		CompletedStages: append([]string(nil), execution.completed...),
		Attributes:      domainAttributes(definition, len(execution.completed)),
	}, nil
}

type executionContext struct {
	definition    Definition
	correlationID string
	authorized    map[string]struct{}
	recorder      Recorder
	completed     []string
	active        string
}

func (e *executionContext) RunStage(
	ctx context.Context,
	name string,
	operation func(context.Context) (any, error),
) (any, error) {
	stage, index, err := e.stage(name)
	if err != nil {
		return nil, err
	}
	if err := e.validateOrder(name, index); err != nil {
		return nil, err
	}
	if stage.SideEffectPolicy == ApprovalRequired {
		if _, authorized := e.authorized[name]; !authorized {
			return nil, &AuthorizationError{Stage: name}
		}
	}
	e.active = name
	if err := e.record(ctx, StageStarted, name, ""); err != nil {
		e.active = ""
		return nil, err
	}
	output, err := operation(ctx)
	e.active = ""
	if err != nil {
		_ = e.record(ctx, StageFailed, name, errorType(err))
		return nil, err
	}
	e.completed = append(e.completed, name)
	if err := e.record(ctx, StageCompleted, name, ""); err != nil {
		return nil, err
	}
	return output, nil
}

func (e *executionContext) stage(name string) (StageDefinition, int, error) {
	for index, stage := range e.definition.Stages {
		if stage.Name == name {
			return stage, index, nil
		}
	}
	return StageDefinition{}, -1, &ContractError{Message: fmt.Sprintf(
		"workflow %q does not declare stage %q",
		e.definition.Name,
		name,
	)}
}

func (e *executionContext) validateOrder(name string, index int) error {
	if e.active != "" {
		return &ContractError{Message: fmt.Sprintf(
			"workflow stage %q is already running",
			e.active,
		)}
	}
	for completedIndex, completed := range e.completed {
		if completed == name {
			return &ContractError{Message: fmt.Sprintf(
				"workflow stage %q cannot run more than once",
				name,
			)}
		}
		if completedIndex == len(e.completed)-1 {
			_, previousIndex, _ := e.stage(completed)
			if index <= previousIndex {
				return &ContractError{Message: fmt.Sprintf(
					"workflow stage %q violates declared stage order",
					name,
				)}
			}
		}
	}
	return nil
}

func (e *executionContext) record(
	ctx context.Context,
	kind EventKind,
	stageName, errorName string,
) error {
	return e.recorder.Record(ctx, Event{
		Kind: kind, WorkflowName: e.definition.Name,
		WorkflowVersion: e.definition.Version, CorrelationID: e.correlationID,
		StageName: stageName, ErrorType: errorName,
	})
}

func validateAuthorizations(definition Definition, authorized map[string]struct{}) error {
	declared := make(map[string]struct{}, len(definition.Stages))
	for _, stage := range definition.Stages {
		declared[stage.Name] = struct{}{}
	}
	for name := range authorized {
		if _, exists := declared[name]; !exists {
			return &ContractError{Message: fmt.Sprintf(
				"workflow %q received authorization for unknown stages: %s",
				definition.Name,
				name,
			)}
		}
	}
	return nil
}

func errorType(err error) string {
	return reflect.TypeOf(err).String()
}
