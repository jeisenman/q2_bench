package oms

import (
	"context"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
)

type fakeQuerySource struct{ calls int }

func (s *fakeQuerySource) Query(
	context.Context,
	Workspace,
	Query,
) (QueryResult, error) {
	s.calls++
	return QueryResult{Columns: []string{"message"}, Rows: [][]any{{"ready"}}}, nil
}

type fakeLogSink struct{ calls int }

func (s *fakeLogSink) Write(context.Context, Workspace, LogRecord) error {
	s.calls++
	return nil
}

func TestWorkspaceRouting(t *testing.T) {
	t.Parallel()
	staging, err := ResolveWorkspace(Staging, US)
	if err != nil {
		t.Fatal(err)
	}
	development, err := ResolveWorkspace(Development, US)
	if err != nil {
		t.Fatal(err)
	}
	if staging != development || staging.Name != "pl-oms-preprod-primary" {
		t.Fatalf("staging = %#v, development = %#v", staging, development)
	}
	if _, err := ResolveWorkspace(Staging, CA); err == nil {
		t.Fatal("expected unsupported Canada staging route")
	}
}

func TestAgentQuery(t *testing.T) {
	t.Parallel()
	source := &fakeQuerySource{}
	agent := Agent{QuerySource: source, LogSink: &fakeLogSink{}}
	result, err := agent.Run(context.Background(), domain.AgentRequest{
		Prompt: "Heartbeat_CL | take 1", CorrelationID: "query-1",
		Attributes: domain.Attributes{
			{Name: "operation", Value: "query"},
			{Name: "environment", Value: "staging"},
			{Name: "region", Value: "us"},
			{Name: "timespan", Value: "PT15M"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	want := `{"columns":["message"],"rows":[["ready"]]}`
	if result.Output != want || source.calls != 1 {
		t.Fatalf("result = %#v, calls = %d", result, source.calls)
	}
}

func TestWritesRequireAuthorization(t *testing.T) {
	t.Parallel()
	record := LogRecord{LogType: "AgentTest", Fields: map[string]any{"message": "test"}}
	if err := (Agent{}).WriteLog(context.Background(), Staging, US, record); err == nil {
		t.Fatal("expected disabled write to fail")
	}
	if err := (Agent{AllowWrites: true, LogSink: &fakeLogSink{}}).WriteLog(
		context.Background(),
		Production,
		US,
		record,
	); err == nil {
		t.Fatal("expected production write to require separate authorization")
	}
}
