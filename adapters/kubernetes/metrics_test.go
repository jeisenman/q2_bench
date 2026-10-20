package kubernetes

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestSnapshotMapsSparkApplicationAndMemory(t *testing.T) {
	t.Parallel()
	var calls [][]string
	source := NewSource(func(
		_ context.Context,
		name string,
		args ...string,
	) ([]byte, error) {
		calls = append(calls, append([]string{name}, args...))
		joined := strings.Join(args, " ")
		switch {
		case strings.Contains(joined, "get pod driver"):
			return []byte(`{
				"metadata":{"name":"driver","labels":{
					"spark-app-selector":"spark-123","spark-role":"driver"
				}},
				"spec":{"containers":[{"name":"main","resources":{
					"limits":{"memory":"6Gi"}
				}}]},
				"status":{"containerStatuses":[{"name":"main","state":{},"lastState":{}}]}
			}`), nil
		case strings.Contains(joined, "get pods --selector"):
			return []byte(`{"items":[
				{
					"metadata":{"name":"driver","labels":{"spark-role":"driver"}},
					"spec":{"containers":[{"name":"main","resources":{
						"limits":{"memory":"6Gi"}
					}}]},
					"status":{"containerStatuses":[{"name":"main","state":{},"lastState":{}}]}
				},
				{
					"metadata":{"name":"executor-1","labels":{"spark-role":"executor"}},
					"spec":{"containers":[{"name":"main","resources":{
						"limits":{"memory":"12Gi"}
					}}]},
					"status":{"containerStatuses":[{"name":"main","state":{},
						"lastState":{"terminated":{"reason":"OOMKilled"}}}]}
				}
			]}`), nil
		case strings.Contains(joined, "get --raw"):
			return []byte(`{"items":[
				{"metadata":{"name":"driver"},"containers":[
					{"name":"main","usage":{"memory":"2Gi"}}
				]},
				{"metadata":{"name":"executor-1"},"containers":[
					{"name":"main","usage":{"memory":"10485760Ki"}}
				]}
			]}`), nil
		default:
			return nil, errors.New("unexpected command")
		}
	})
	source.Now = func() time.Time {
		return time.Date(2026, 10, 15, 19, 0, 0, 0, time.UTC)
	}
	snapshot, err := source.Snapshot(
		context.Background(),
		"l3-us01",
		"scheduler",
		"driver",
	)
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.ApplicationSelector != "spark-123" ||
		len(snapshot.Pods) != 2 ||
		snapshot.Pods[1].MemoryBytes != 10<<30 ||
		!snapshot.Pods[1].OOMKilled {
		t.Fatalf("snapshot = %#v", snapshot)
	}
	if len(calls) != 3 {
		t.Fatalf("calls = %#v", calls)
	}
}

func TestSnapshotReturnsTypedPodNotFound(t *testing.T) {
	t.Parallel()
	source := NewSource(func(
		context.Context,
		string,
		...string,
	) ([]byte, error) {
		return []byte(`Error from server (NotFound): pods "missing" not found`),
			errors.New("exit status 1")
	})
	_, err := source.Snapshot(
		context.Background(),
		"l3-us01",
		"scheduler",
		"missing",
	)
	var notFound *PodNotFoundError
	if !errors.As(err, &notFound) {
		t.Fatalf("error = %v", err)
	}
}

func TestParseMemoryQuantity(t *testing.T) {
	t.Parallel()
	tests := map[string]uint64{
		"14509360Ki": 14509360 << 10,
		"5734Mi":     5734 << 20,
		"1.5Gi":      3 << 29,
		"40G":        40_000_000_000,
		"1024":       1024,
	}
	for input, want := range tests {
		got, err := ParseMemoryQuantity(input)
		if err != nil {
			t.Errorf("%s: %v", input, err)
			continue
		}
		if got != want {
			t.Errorf("%s = %d, want %d", input, got, want)
		}
	}
	if _, err := ParseMemoryQuantity("not-memory"); err == nil {
		t.Fatal("invalid memory quantity was accepted")
	}
}

func TestMakeSnapshotOrdersRolesAndWarnsOnMissingMetrics(t *testing.T) {
	t.Parallel()
	var executor kubernetesPod
	executor.Metadata.Name = "executor"
	executor.Metadata.Labels = map[string]string{"spark-role": "executor"}
	var driver kubernetesPod
	driver.Metadata.Name = "driver"
	driver.Metadata.Labels = map[string]string{"spark-role": "driver"}
	snapshot, err := makeSnapshot(
		time.Date(2026, 10, 15, 19, 0, 0, 0, time.UTC),
		"driver",
		"spark-123",
		[]kubernetesPod{executor, driver},
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	roles := []string{snapshot.Pods[0].Role, snapshot.Pods[1].Role}
	if !reflect.DeepEqual(roles, []string{"driver", "executor"}) ||
		len(snapshot.Warnings) != 2 {
		t.Fatalf("snapshot = %#v", snapshot)
	}
}
