package mcpapi

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/adapters/airflow"
	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

type followUpGuardTransport struct {
	dagStatus any
	dagError  error
	dagCalls  int
}

func (t *followUpGuardTransport) Request(
	_ context.Context,
	_ airflow.Credentials,
	method, path string,
	_ map[string]any,
) (any, error) {
	if method != "GET" {
		return nil, errors.New("unexpected mutation")
	}
	switch path {
	case "/api/v1/dags?limit=1&only_active=true":
		return map[string]any{"total_entries": 209}, nil
	case "/api/v1/dags/dag":
		t.dagCalls++
		return t.dagStatus, t.dagError
	default:
		return nil, errors.New("unexpected Airflow path")
	}
}

func TestFollowUpPreflightDoesNotRequireKubectlClusterCheck(t *testing.T) {
	t.Parallel()
	transport := &followUpGuardTransport{
		dagStatus: map[string]any{"is_paused": false},
	}
	api := followUpGuardAPI(transport, `{"items":[]}`)

	if err := api.preflightFollowUp(context.Background(), guardBatches()); err != nil {
		t.Fatal(err)
	}
	if transport.dagCalls != 1 {
		t.Fatalf("DAG checks = %d", transport.dagCalls)
	}
}

func TestFollowUpPreflightAcceptsMissingClusterGuard(t *testing.T) {
	t.Parallel()
	transport := &followUpGuardTransport{
		dagStatus: map[string]any{"is_paused": false},
	}
	source := airflow.NewSource([]airflow.RegionConfig{{
		Region: prodsupport.US01, Credentials: airflow.Credentials{},
	}}, transport)
	api := &prodSupportAPI{airflow: &airflowAPI{source: source}}

	if err := api.preflightFollowUp(context.Background(), guardBatches()); err != nil {
		t.Fatal(err)
	}
}

func TestFollowUpPreflightBlocksMissingOrPausedDAG(t *testing.T) {
	t.Parallel()
	tests := map[string]struct {
		status any
		err    error
		want   string
	}{
		"missing": {
			err:  &airflow.HTTPStatusError{StatusCode: 404},
			want: "DAG dag does not exist",
		},
		"paused": {
			status: map[string]any{"is_paused": true},
			want:   "DAG dag is paused",
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			transport := &followUpGuardTransport{
				dagStatus: test.status,
				dagError:  test.err,
			}
			api := followUpGuardAPI(transport, healthyPodList)

			err := api.preflightFollowUp(context.Background(), guardBatches())
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v", err)
			}
			if transport.dagCalls != 1 {
				t.Fatalf("DAG checks = %d", transport.dagCalls)
			}
		})
	}
}

func TestFollowUpPreflightAcceptsExistingClusterAndActiveDAG(t *testing.T) {
	t.Parallel()
	transport := &followUpGuardTransport{
		dagStatus: map[string]any{"is_paused": false},
	}
	api := followUpGuardAPI(transport, healthyPodList)

	if err := api.preflightFollowUp(context.Background(), guardBatches()); err != nil {
		t.Fatal(err)
	}
	if transport.dagCalls != 1 {
		t.Fatalf("DAG checks = %d", transport.dagCalls)
	}
}

const healthyPodList = `{
	"items": [{
		"metadata": {"name": "airflow-worker"},
		"status": {
			"phase": "Running",
			"containerStatuses": [{"ready": true, "restartCount": 0}]
		}
	}]
}`

func followUpGuardAPI(
	transport airflow.Transport,
	pods string,
) *prodSupportAPI {
	source := airflow.NewSource([]airflow.RegionConfig{{
		Region: prodsupport.US01, Credentials: airflow.Credentials{},
	}}, transport)
	airflowAPI := &airflowAPI{source: source}
	return &prodSupportAPI{
		airflow: airflowAPI,
		cluster: &clusterHealthAPI{
			airflow: airflowAPI,
			run: func(context.Context, string, ...string) ([]byte, error) {
				return []byte(pods), nil
			},
		},
	}
}

func guardBatches() []prodsupport.RetryBatch {
	return []prodsupport.RetryBatch{{
		Region: prodsupport.US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskIDs: []string{
			"task",
		},
	}}
}
