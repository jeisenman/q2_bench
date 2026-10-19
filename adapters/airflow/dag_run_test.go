package airflow

import (
	"context"
	"testing"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

func TestGetDAGRunStateReadsExactRun(t *testing.T) {
	t.Parallel()
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01,
		Credentials: Credentials{
			Host: "https://airflow",
		},
	}}, transportFunc(func(
		_ context.Context,
		_ Credentials,
		method, path string,
		_ map[string]any,
	) (any, error) {
		if method != "GET" ||
			path != "/api/v1/dags/dag/dagRuns/manual__2026-10-11T05:00:00+00:00" {
			t.Fatalf("unexpected request %s %s", method, path)
		}
		return map[string]any{"state": "success"}, nil
	}))

	state, err := source.GetDAGRunState(
		context.Background(),
		prodsupport.US01,
		"dag",
		"manual__2026-10-11T05:00:00+00:00",
	)
	if err != nil {
		t.Fatal(err)
	}
	if state != "success" {
		t.Fatalf("state = %q", state)
	}
}

func TestGetDAGRunStateRejectsMissingState(t *testing.T) {
	t.Parallel()
	source := NewSource([]RegionConfig{{
		Region: prodsupport.US01,
		Credentials: Credentials{
			Host: "https://airflow",
		},
	}}, transportFunc(func(
		context.Context,
		Credentials,
		string,
		string,
		map[string]any,
	) (any, error) {
		return map[string]any{"state": nil}, nil
	}))

	if _, err := source.GetDAGRunState(
		context.Background(),
		prodsupport.US01,
		"dag",
		"run",
	); err == nil {
		t.Fatal("expected missing state to fail")
	}
}
