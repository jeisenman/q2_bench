package agents

import (
	"context"
	"reflect"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
)

func TestScaffoldedAgentsReturnDeterministicPlans(t *testing.T) {
	t.Parallel()
	scaffolds := []*PlanningAgent{
		NewKPOSizer(),
		NewETL(),
		NewDataFinder(),
		NewDataCreator(),
		NewDataInsightTriage(),
		NewBenchmarkBuilder(),
	}
	request := domain.AgentRequest{
		Prompt: "Build the requested workflow.", CorrelationID: "scaffold-test",
	}
	for _, agent := range scaffolds {
		first, err := agent.Run(context.Background(), request)
		if err != nil {
			t.Fatal(err)
		}
		second, err := agent.Run(context.Background(), request)
		if err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(first, second) {
			t.Fatalf("%s result was not deterministic", agent.Definition().Name)
		}
		if !strings.HasPrefix(first.Output, "Objective: Build the requested workflow.\nPlan:") {
			t.Fatalf("%s output = %q", agent.Definition().Name, first.Output)
		}
	}
}

func TestRegistry(t *testing.T) {
	t.Parallel()
	registry := NewRegistry()
	if err := registry.Register("etl", func() Agent { return NewETL() }); err != nil {
		t.Fatal(err)
	}
	if err := registry.Register("etl", func() Agent { return NewETL() }); err == nil {
		t.Fatal("expected duplicate registration to fail")
	}
	if _, err := registry.Create("missing"); err == nil {
		t.Fatal("expected unknown agent to fail")
	}
	if got := registry.Names(); !reflect.DeepEqual(got, []string{"etl"}) {
		t.Fatalf("Names() = %v", got)
	}
}
