package airflow

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// DAGStatus describes whether one DAG currently exists and is active.
type DAGStatus struct {
	Exists   bool
	IsPaused bool
}

// GetDAGStatus checks whether one exact DAG currently exists.
func (s *Source) GetDAGStatus(
	ctx context.Context,
	region prodsupport.Region,
	dagID string,
) (DAGStatus, error) {
	if strings.TrimSpace(dagID) == "" {
		return DAGStatus{}, fmt.Errorf("Airflow DAG ID must not be empty")
	}
	config, err := s.configFor(region)
	if err != nil {
		return DAGStatus{}, err
	}
	response, err := RequestWithTransientRetry(
		ctx,
		s.Transport,
		config.Credentials,
		"GET",
		"/api/v1/dags/"+url.PathEscape(dagID),
		nil,
		s.Sleep,
	)
	if err != nil {
		var statusErr *HTTPStatusError
		if errors.As(err, &statusErr) && statusErr.StatusCode == http.StatusNotFound {
			return DAGStatus{Exists: false}, nil
		}
		return DAGStatus{}, err
	}
	payload, ok := response.(map[string]any)
	if !ok {
		return DAGStatus{}, fmt.Errorf("Airflow DAG response must be an object")
	}
	paused, ok := payload["is_paused"].(bool)
	if !ok {
		return DAGStatus{}, fmt.Errorf("Airflow DAG response is missing is_paused")
	}
	return DAGStatus{Exists: true, IsPaused: paused}, nil
}

// ActiveDAGCount returns the number of currently active DAGs in one region.
func (s *Source) ActiveDAGCount(
	ctx context.Context,
	region prodsupport.Region,
) (int, error) {
	config, err := s.configFor(region)
	if err != nil {
		return 0, err
	}
	response, err := RequestWithTransientRetry(
		ctx,
		s.Transport,
		config.Credentials,
		"GET",
		"/api/v1/dags?limit=1&only_active=true",
		nil,
		s.Sleep,
	)
	if err != nil {
		return 0, err
	}
	payload, ok := response.(map[string]any)
	if !ok {
		return 0, fmt.Errorf("Airflow DAG response must be an object")
	}
	count, ok := integer(payload["total_entries"])
	if !ok || count < 0 {
		return 0, fmt.Errorf("Airflow DAG response is missing total_entries")
	}
	return count, nil
}
