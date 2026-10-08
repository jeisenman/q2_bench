package mcpapi

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
)

type fakeCortex struct {
	environment domain.Environment
	request     ports.CortexRequest
}

func (f *fakeCortex) Environment() domain.Environment {
	return f.environment
}

func (f *fakeCortex) Complete(
	_ context.Context,
	request ports.CortexRequest,
) (ports.CortexResponse, error) {
	f.request = request
	return ports.CortexResponse{
		Text: "complete", Model: request.Model, Environment: f.environment,
		Recorded: f.environment.Deterministic(),
	}, nil
}

func (*fakeCortex) CountTokens(context.Context, string, string) (int, error) {
	return 7, nil
}

func TestRunCortexCompleteReportsExecutionMode(t *testing.T) {
	t.Parallel()
	fake := &fakeCortex{environment: domain.EnvironmentSandbox}
	api := &warehouseAPI{resolve: func(
		environment domain.Environment,
	) (ports.CortexInference, error) {
		if environment != domain.EnvironmentSandbox {
			return nil, errors.New("unexpected environment")
		}
		return fake, nil
	}}
	_, output, err := api.runCortexComplete(
		context.Background(),
		nil,
		cortexCompleteInput{
			Model: "model", Prompt: "prompt", Temperature: 0.25,
			Environment: "sandbox",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if output["completion"] != "complete" || output["recorded"] != true {
		t.Fatalf("output = %#v", output)
	}
	if fake.request.Temperature != 0.25 {
		t.Fatalf("request = %#v", fake.request)
	}
}

func TestRunCortexCompleteRejectsOversizedPromptBeforeResolution(t *testing.T) {
	t.Parallel()
	api := &warehouseAPI{resolve: func(
		domain.Environment,
	) (ports.CortexInference, error) {
		t.Fatal("resolver should not be called")
		return nil, nil
	}}
	_, _, err := api.runCortexComplete(
		context.Background(),
		nil,
		cortexCompleteInput{
			Model: "model", Prompt: strings.Repeat("x", ports.MaxCortexPromptBytes+1),
		},
	)
	if err == nil || !strings.Contains(err.Error(), "must not exceed") {
		t.Fatalf("err = %v", err)
	}
}

func TestRequestedEnvironmentDefaultsToSandbox(t *testing.T) {
	t.Setenv("WAREHOUSE_ENVIRONMENT", "")
	environment, err := requestedEnvironment("")
	if err != nil {
		t.Fatal(err)
	}
	if environment != domain.EnvironmentSandbox {
		t.Fatalf("environment = %q", environment)
	}
}
