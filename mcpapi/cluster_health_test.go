package mcpapi

import (
	"context"
	"testing"
	"time"

	"github.com/jeisenman/q2_bench/adapters/airflow"
	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

func TestParsePodHealthCountsWindowedAndCumulativeRestarts(t *testing.T) {
	t.Parallel()
	content := []byte(`{
		"items": [
			{
				"metadata": {"name": "airflow-dag-processor-1"},
				"status": {
					"phase": "Running",
					"containerStatuses": [{
						"ready": false,
						"restartCount": 3,
						"lastState": {
							"terminated": {"finishedAt": "2026-10-13T06:00:00Z"}
						}
					}]
				}
			},
			{
				"metadata": {"name": "completed"},
				"status": {"phase": "Succeeded", "containerStatuses": []}
			}
		]
	}`)
	startAt := time.Date(2026, 10, 13, 5, 0, 0, 0, time.UTC)
	endAt := startAt.Add(24 * time.Hour)
	health, err := parsePodHealth(content, startAt, endAt)
	if err != nil {
		t.Fatal(err)
	}
	if health.podsHealthy || health.restartCount != 1 ||
		health.cumulativeRestartCount != 3 ||
		len(health.unreadyPods) != 1 {
		t.Fatalf("health = %#v", health)
	}
}

func TestInspectClusterHealthIncludesActiveDAGCount(t *testing.T) {
	t.Parallel()
	source := airflow.NewSource([]airflow.RegionConfig{{
		Region: prodsupport.US01, Credentials: airflow.Credentials{},
	}}, clusterAirflowTransport{})
	api := &clusterHealthAPI{
		airflow: &airflowAPI{source: source},
		run: func(context.Context, string, ...string) ([]byte, error) {
			return []byte(`{
				"items": [{
					"metadata": {"name": "airflow-worker"},
					"status": {
						"phase": "Running",
						"containerStatuses": [{
							"ready": true,
							"restartCount": 0,
							"lastState": {"terminated": {}}
						}]
					}
				}]
			}`), nil
		},
	}
	_, output, err := api.inspect(
		context.Background(),
		nil,
		inspectClusterHealthInput{
			Region: "US-01", StartAt: "2026-10-13T05:00:00Z",
			EndAt: "2026-10-14T05:00:00Z",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if output["cluster_exists"] != true || output["active_dag_count"] != 209 ||
		output["healthy"] != true {
		t.Fatalf("output = %#v", output)
	}
}

type clusterAirflowTransport struct{}

func (clusterAirflowTransport) Request(
	_ context.Context,
	_ airflow.Credentials,
	method, path string,
	_ map[string]any,
) (any, error) {
	if method != "GET" || path != "/api/v1/dags?limit=1&only_active=true" {
		return nil, &airflow.HTTPStatusError{StatusCode: 500}
	}
	return map[string]any{"dags": []any{}, "total_entries": 209}, nil
}
