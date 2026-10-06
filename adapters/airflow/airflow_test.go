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
	return map[string]any{
		"task_instances": []any{map[string]any{
			"dag_id": "dag", "dag_run_id": "run", "task_id": "task", "state": "failed",
		}},
	}, nil
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
	if references[0].Region != prodsupport.CA02 || transport.payloads[0]["dry_run"] != true {
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
