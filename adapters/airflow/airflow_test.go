package airflow

import (
	"context"
	"reflect"
	"testing"
	"time"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

type fakeTransport struct {
	payloads []map[string]any
	expanded bool
}

func (t *fakeTransport) Request(
	_ context.Context,
	_ Credentials,
	method, _ string,
	payload map[string]any,
) (any, error) {
	t.payloads = append(t.payloads, payload)
	if method == "GET" {
		return map[string]any{"state": "queued"}, nil
	}
	items := []any{map[string]any{
		"dag_id": "dag", "dag_run_id": "run", "task_id": "task", "state": "failed",
	}}
	if t.expanded {
		items = append(items, map[string]any{
			"dag_id": "dag", "dag_run_id": "run",
			"task_id": "downstream", "state": "failed",
		})
	}
	return map[string]any{"task_instances": items}, nil
}

func TestRetryUsesExactSafePayload(t *testing.T) {
	t.Parallel()
	transport := &fakeTransport{}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.CA02, DAGID: "dag", RunID: "run", TaskIDs: []string{"task"},
	}
	references, err := PlanRetry(
		context.Background(),
		batch,
		Credentials{},
		transport,
	)
	if err != nil {
		t.Fatal(err)
	}
	if references[0].Region != prodsupport.CA02 ||
		transport.payloads[0]["dry_run"] != true ||
		transport.payloads[0]["include_downstream"] != true {
		t.Fatalf("references = %#v, payload = %#v", references, transport.payloads[0])
	}
}

func TestExecuteRetryRevalidatesAndReadsState(t *testing.T) {
	t.Parallel()
	transport := &fakeTransport{}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01, DAGID: "dag", RunID: "run", TaskIDs: []string{"task"},
	}
	states, err := ExecuteRetry(
		context.Background(),
		batch,
		"approval-1",
		Credentials{},
		transport,
		func(context.Context, string) (any, error) {
			return map[string]any{"state": "queued"}, nil
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if states[0].State != "queued" {
		t.Fatalf("states = %#v", states)
	}
	if got := []any{transport.payloads[0]["dry_run"], transport.payloads[1]["dry_run"]}; !reflect.DeepEqual(got, []any{true, false}) {
		t.Fatalf("dry runs = %#v", got)
	}
}

func TestExecuteRetryReadsApprovedDownstreamExpansion(t *testing.T) {
	t.Parallel()
	transport := &fakeTransport{expanded: true}
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01, DAGID: "dag", RunID: "run", TaskIDs: []string{"task"},
	}
	read := make([]string, 0, 2)
	states, err := ExecuteRetry(
		context.Background(),
		batch,
		"approval-1",
		Credentials{},
		transport,
		func(_ context.Context, taskID string) (any, error) {
			read = append(read, taskID)
			return map[string]any{"state": "queued"}, nil
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(states) != 2 || !reflect.DeepEqual(read, []string{"downstream", "task"}) {
		t.Fatalf("states = %#v, read = %#v", states, read)
	}
}

func TestPlanRetryRejectsTaskFromAnotherDAGRun(t *testing.T) {
	t.Parallel()
	transport := &fakeTransport{}
	transport.payloads = nil
	batch := prodsupport.RetryBatch{
		Region: prodsupport.US01, DAGID: "dag", RunID: "run", TaskIDs: []string{"task"},
	}
	response := map[string]any{"task_instances": []any{
		map[string]any{
			"dag_id": "other-dag", "dag_run_id": "run",
			"task_id": "task", "state": "failed",
		},
	}}
	if _, err := references(response, batch); err == nil {
		t.Fatal("expected cross-DAG response to fail")
	}
}

func TestGetTaskStateReadsExactTaskInstance(t *testing.T) {
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01, Credentials: Credentials{Host: "https://airflow"},
	}}, transportFunc(func(
		_ context.Context,
		_ Credentials,
		method string,
		path string,
		_ map[string]any,
	) (any, error) {
		if method != "GET" ||
			path != "/api/v1/dags/dag/dagRuns/run/taskInstances/task" {
			t.Fatalf("unexpected request %s %s", method, path)
		}
		return map[string]any{"state": "running"}, nil
	}))

	state, err := source.GetTaskState(
		context.Background(), prodsupport.US01, "dag", "run", "task",
	)
	if err != nil {
		t.Fatal(err)
	}
	if state != "running" {
		t.Fatalf("state = %q", state)
	}
}

func TestGetTaskStateNormalizesEmptyState(t *testing.T) {
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01, Credentials: Credentials{Host: "https://airflow"},
	}}, transportFunc(func(
		_ context.Context,
		_ Credentials,
		_ string,
		_ string,
		_ map[string]any,
	) (any, error) {
		return map[string]any{"state": nil}, nil
	}))

	state, err := source.GetTaskState(
		context.Background(), prodsupport.US01, "dag", "run", "task",
	)
	if err != nil {
		t.Fatal(err)
	}
	if state != "unknown" {
		t.Fatalf("state = %q", state)
	}
}

func TestGetTaskInstanceReturnsAttemptAndTimestamps(t *testing.T) {
	t.Parallel()
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01, Credentials: Credentials{Host: "https://airflow"},
	}}, transportFunc(func(
		_ context.Context,
		_ Credentials,
		_ string,
		_ string,
		_ map[string]any,
	) (any, error) {
		return map[string]any{
			"state":      "running",
			"try_number": 7,
			"start_date": "2026-10-15T19:00:00Z",
			"end_date":   nil,
		}, nil
	}))

	instance, err := source.GetTaskInstance(
		context.Background(), prodsupport.US01, "dag", "run", "task",
	)
	if err != nil {
		t.Fatal(err)
	}
	if instance.State != "running" || instance.TryNumber != 7 ||
		instance.StartAt == nil || instance.EndAt != nil {
		t.Fatalf("instance = %#v", instance)
	}
}

func TestTransientRetry(t *testing.T) {
	t.Parallel()
	attempts := 0
	transport := transportFunc(func(
		context.Context,
		Credentials,
		string,
		string,
		map[string]any,
	) (any, error) {
		attempts++
		if attempts < 3 {
			return nil, &HTTPStatusError{StatusCode: 503}
		}
		return map[string]any{}, nil
	})
	sleeps := 0
	_, err := RequestWithTransientRetry(
		context.Background(),
		transport,
		Credentials{},
		"GET",
		"/",
		nil,
		func(context.Context, time.Duration) error {
			sleeps++
			return nil
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if attempts != 3 || sleeps != 2 {
		t.Fatalf("attempts = %d, sleeps = %d", attempts, sleeps)
	}
}

func TestTaskInstancesAcceptsIntegerTotal(t *testing.T) {
	t.Parallel()
	items, total, err := taskInstances(map[string]any{
		"task_instances": []any{map[string]any{"task_id": "validate"}},
		"total_entries":  1,
	})
	if err != nil {
		t.Fatalf("taskInstances returned an error: %v", err)
	}
	if total != 1 || len(items) != 1 {
		t.Fatalf("unexpected page: total=%d items=%d", total, len(items))
	}
}

func TestTaskInstancesRejectsFractionalTotal(t *testing.T) {
	t.Parallel()
	_, _, err := taskInstances(map[string]any{
		"task_instances": []any{},
		"total_entries":  1.5,
	})
	if err == nil {
		t.Fatal("taskInstances accepted a fractional total")
	}
}

func TestHasSuccessWithinUsesHalfOpenWindow(t *testing.T) {
	t.Parallel()
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01, Credentials: Credentials{},
	}}, transportFunc(func(
		_ context.Context,
		_ Credentials,
		method, path string,
		payload map[string]any,
	) (any, error) {
		if method != "POST" ||
			path != "/api/v1/dags/~/dagRuns/~/taskInstances/list" {
			t.Fatalf("unexpected request %s %s", method, path)
		}
		if payload["state"].([]string)[0] != "success" {
			t.Fatalf("payload = %#v", payload)
		}
		return map[string]any{
			"task_instances": []any{map[string]any{
				"dag_id": "dag", "task_id": "task",
				"end_date": "2026-09-25T06:00:00Z",
			}},
			"total_entries": 1,
		}, nil
	}))
	failure := prodsupport.AirflowFailure{
		Region: prodsupport.US01, DAGID: "dag", RunID: "run", TaskID: "task",
		StartAt: time.Date(2026, 9, 25, 5, 0, 0, 0, time.UTC),
		EndAt:   time.Date(2026, 9, 25, 5, 30, 0, 0, time.UTC), TryNumber: 1,
	}
	recovered, err := source.HasSuccessWithin(
		context.Background(),
		failure,
		time.Date(2026, 9, 25, 5, 0, 0, 0, time.UTC),
		time.Date(2026, 9, 25, 7, 0, 0, 0, time.UTC),
	)
	if err != nil {
		t.Fatal(err)
	}
	if !recovered {
		t.Fatal("expected matching success")
	}
}

func TestGetDAGStatusReturnsMissingForNotFound(t *testing.T) {
	t.Parallel()
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01, Credentials: Credentials{},
	}}, transportFunc(func(
		context.Context,
		Credentials,
		string,
		string,
		map[string]any,
	) (any, error) {
		return nil, &HTTPStatusError{StatusCode: 404}
	}))
	status, err := source.GetDAGStatus(
		context.Background(),
		prodsupport.US01,
		"retired-dag",
	)
	if err != nil {
		t.Fatal(err)
	}
	if status.Exists {
		t.Fatalf("status = %#v", status)
	}
}

func TestActiveDAGCountReadsTotalEntries(t *testing.T) {
	t.Parallel()
	source := NewSource([]RegionConfig{{
		Region: prodsupport.CA02, Credentials: Credentials{},
	}}, transportFunc(func(
		_ context.Context,
		_ Credentials,
		method, path string,
		_ map[string]any,
	) (any, error) {
		if method != "GET" || path != "/api/v1/dags?limit=1&only_active=true" {
			t.Fatalf("unexpected request %s %s", method, path)
		}
		return map[string]any{"dags": []any{}, "total_entries": 34}, nil
	}))
	count, err := source.ActiveDAGCount(context.Background(), prodsupport.CA02)
	if err != nil {
		t.Fatal(err)
	}
	if count != 34 {
		t.Fatalf("count = %d", count)
	}
}

type transportFunc func(
	context.Context,
	Credentials,
	string,
	string,
	map[string]any,
) (any, error)

func (f transportFunc) Request(
	ctx context.Context,
	credentials Credentials,
	method, path string,
	payload map[string]any,
) (any, error) {
	return f(ctx, credentials, method, path, payload)
}
