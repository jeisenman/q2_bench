package workflowharness

import (
	"context"
	"errors"
	"testing"
)

type exampleWorkflow struct{}

func (exampleWorkflow) Definition() Definition {
	return Definition{
		Name: "example", Description: "Run an example.", Version: "2",
		Stages: []StageDefinition{
			{Name: "inspect", Description: "Inspect input."},
			{
				Name: "change", Description: "Apply an approved change.",
				SideEffectPolicy: ApprovalRequired,
			},
		},
	}
}

func (exampleWorkflow) Execute(
	ctx context.Context,
	request Request[string],
	execution ExecutionContext,
) (string, error) {
	inspected, err := execution.RunStage(ctx, "inspect", func(context.Context) (any, error) {
		return "inspected:" + request.Input, nil
	})
	if err != nil {
		return "", err
	}
	if _, authorized := request.AuthorizedStages["change"]; !authorized {
		return inspected.(string), nil
	}
	changed, err := execution.RunStage(ctx, "change", func(context.Context) (any, error) {
		return "changed:" + inspected.(string), nil
	})
	if err != nil {
		return "", err
	}
	return changed.(string), nil
}

func TestRunnerRecordsReadOnlyWorkflow(t *testing.T) {
	t.Parallel()
	recorder := &InMemoryRecorder{}
	result, err := Run(
		context.Background(),
		Runner{Recorder: recorder},
		exampleWorkflow{},
		Request[string]{Input: "data", CorrelationID: "run-1"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.Output != "inspected:data" || len(result.CompletedStages) != 1 {
		t.Fatalf("result = %#v", result)
	}
	wantKinds := []EventKind{RunStarted, StageStarted, StageCompleted, RunCompleted}
	for index, event := range recorder.Events {
		if event.Kind != wantKinds[index] {
			t.Fatalf("event %d kind = %q", index, event.Kind)
		}
	}
}

func TestRunnerExecutesAuthorizedStage(t *testing.T) {
	t.Parallel()
	result, err := Run(
		context.Background(),
		Runner{},
		exampleWorkflow{},
		Request[string]{
			Input: "data", CorrelationID: "run-2",
			AuthorizedStages: map[string]struct{}{"change": {}},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.Output != "changed:inspected:data" || len(result.CompletedStages) != 2 {
		t.Fatalf("result = %#v", result)
	}
}

type unsafeWorkflow struct{ exampleWorkflow }

func (unsafeWorkflow) Execute(
	ctx context.Context,
	_ Request[string],
	execution ExecutionContext,
) (string, error) {
	_, err := execution.RunStage(ctx, "change", func(context.Context) (any, error) {
		return "changed", nil
	})
	return "", err
}

func TestRunnerRejectsUnauthorizedStage(t *testing.T) {
	t.Parallel()
	_, err := Run(
		context.Background(),
		Runner{},
		unsafeWorkflow{},
		Request[string]{Input: "data", CorrelationID: "run-3"},
	)
	var authorizationError *AuthorizationError
	if !errors.As(err, &authorizationError) {
		t.Fatalf("expected AuthorizationError, got %v", err)
	}
}
