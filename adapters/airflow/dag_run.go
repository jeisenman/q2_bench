package airflow

import (
	"context"
	"fmt"
	"net/url"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// GetDAGRunState reads one exact Airflow DAG-run state.
func (s *Source) GetDAGRunState(
	ctx context.Context,
	region prodsupport.Region,
	dagID, runID string,
) (string, error) {
	config, err := s.configFor(region)
	if err != nil {
		return "", err
	}
	path := fmt.Sprintf(
		"/api/v1/dags/%s/dagRuns/%s",
		url.PathEscape(dagID),
		url.PathEscape(runID),
	)
	response, err := RequestWithTransientRetry(
		ctx,
		s.Transport,
		config.Credentials,
		"GET",
		path,
		nil,
		s.Sleep,
	)
	if err != nil {
		return "", err
	}
	payload, ok := response.(map[string]any)
	if !ok {
		return "", fmt.Errorf("Airflow DAG-run state response must be an object")
	}
	state := fmt.Sprint(payload["state"])
	if state == "" || state == "<nil>" {
		return "", fmt.Errorf("Airflow DAG-run state response is missing state")
	}
	return state, nil
}
