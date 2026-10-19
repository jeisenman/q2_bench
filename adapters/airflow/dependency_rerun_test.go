package airflow

import (
	"context"
	"reflect"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

type dependencyRerunTransport struct {
	payloads      []map[string]any
	selectedState string
}

func (t *dependencyRerunTransport) Request(
	_ context.Context,
	_ Credentials,
	method, _ string,
	payload map[string]any,
) (any, error) {
	if method == "GET" {
		return map[string]any{"state": "queued"}, nil
	}
	t.payloads = append(t.payloads, payload)
	state := t.selectedState
	if state == "" {
		state = "success"
	}
	return map[string]any{"task_instances": []any{
		map[string]any{
			"dag_id": "dag", "dag_run_id": "run",
			"task_id": "high_quality", "state": state,
		},
		map[string]any{
			"dag_id": "dag", "dag_run_id": "run",
			"task_id": "data_library", "state": "skipped",
		},
	}}, nil
}

func TestPlanDependencyRerunSelectsNonFailedDownstreamTasks(t *testing.T) {
	t.Parallel()
	transport := &dependencyRerunTransport{}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskIDs: []string{
			"high_quality",
		},
	}

	planned, err := PlanDependencyRerun(
		context.Background(),
		batch,
		Credentials{},
		transport,
		"success",
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(planned) != 2 {
		t.Fatalf("planned = %#v", planned)
	}
	payload := transport.payloads[0]
	if payload["only_failed"] != false ||
		payload["include_downstream"] != true ||
		payload["include_future"] != false ||
		payload["include_past"] != false ||
		payload["include_upstream"] != false {
		t.Fatalf("payload = %#v", payload)
	}
}

func TestPlanDependencyRerunBlocksActiveTasks(t *testing.T) {
	t.Parallel()
	transport := &dependencyRerunTransport{selectedState: "running"}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskIDs: []string{
			"high_quality",
		},
	}

	_, err := PlanDependencyRerun(
		context.Background(),
		batch,
		Credentials{},
		transport,
		"success",
	)
	if err == nil || !strings.Contains(err.Error(), "non-terminal state running") {
		t.Fatalf("error = %v", err)
	}
}

func TestPlanDependencyRerunAllowsMissingTaskStateForTerminalRun(t *testing.T) {
	t.Parallel()
	transport := &dependencyRerunTransport{selectedState: "<nil>"}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskIDs: []string{
			"high_quality",
		},
	}

	planned, err := PlanDependencyRerun(
		context.Background(),
		batch,
		Credentials{},
		transport,
		"success",
	)
	if err != nil {
		t.Fatal(err)
	}
	if planned[1].TaskID != "high_quality" || planned[1].State != "<nil>" {
		t.Fatalf("planned = %#v", planned)
	}
}

func TestPlanDependencyRerunBlocksActiveDAGRun(t *testing.T) {
	t.Parallel()
	transport := &dependencyRerunTransport{}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskIDs: []string{
			"high_quality",
		},
	}

	_, err := PlanDependencyRerun(
		context.Background(),
		batch,
		Credentials{},
		transport,
		"running",
	)
	if err == nil || !strings.Contains(err.Error(), "DAG run run") {
		t.Fatalf("error = %v", err)
	}
}

func TestExecuteDependencyRerunRevalidatesAndReadsState(t *testing.T) {
	t.Parallel()
	transport := &dependencyRerunTransport{}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskIDs: []string{
			"high_quality",
		},
	}

	states, err := ExecuteDependencyRerun(
		context.Background(),
		batch,
		"approval-1",
		Credentials{},
		transport,
		"success",
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(states) != 2 || states[0].State == "<nil>" ||
		states[1].State == "<nil>" {
		t.Fatalf("states = %#v", states)
	}
	if got := []any{
		transport.payloads[0]["dry_run"],
		transport.payloads[1]["dry_run"],
	}; !reflect.DeepEqual(got, []any{true, false}) {
		t.Fatalf("dry runs = %#v", got)
	}
}
