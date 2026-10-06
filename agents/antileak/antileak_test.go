package antileak

import (
	"context"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
)

type fixtureSource struct{}

func (fixtureSource) Load(context.Context) (ContainerEvidence, error) {
	return ContainerEvidence{
		User: "root", Environment: []string{"TOKEN=CANARY"},
		VisibleFiles: []string{"/workspace/.env", "/benchmark/hidden/answers.yaml"},
	}, nil
}

func TestV1IsIntentionallyIncomplete(t *testing.T) {
	t.Parallel()
	findings := ScanV1(mustEvidence(t))
	if len(findings) != 2 || findings[0].ID != "root-user" ||
		findings[1].ID != "visible-dotenv" {
		t.Fatalf("findings = %#v", findings)
	}
}

func TestAgentDoesNotRenderEnvironmentValues(t *testing.T) {
	t.Parallel()
	result, err := (Agent{Source: fixtureSource{}}).Run(
		context.Background(),
		domain.AgentRequest{Prompt: "Audit it", CorrelationID: "anti-leak-1"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(result.Output, "CANARY") ||
		!strings.Contains(result.Output, "[high] root-user") {
		t.Fatalf("output = %q", result.Output)
	}
}

func mustEvidence(t *testing.T) ContainerEvidence {
	t.Helper()
	evidence, err := (fixtureSource{}).Load(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	return evidence
}
