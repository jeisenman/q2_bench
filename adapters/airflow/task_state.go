package airflow

import (
	"context"
	"fmt"
	"net/url"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// GetTaskState reads the current state of one exact Airflow task instance.
func (s *Source) GetTaskState(
	ctx context.Context,
	region prodsupport.Region,
	dagID, runID, taskID string,
) (string, error) {
	for name, value := range map[string]string{
		"dag_id": dagID, "run_id": runID, "task_id": taskID,
	} {
		if strings.TrimSpace(value) == "" {
			return "", fmt.Errorf("%s must not be empty", name)
		}
	}
	config, err := s.configFor(region)
	if err != nil {
		return "", err
	}
	path := fmt.Sprintf(
		"/api/v1/dags/%s/dagRuns/%s/taskInstances/%s",
		url.PathEscape(dagID),
		url.PathEscape(runID),
		url.PathEscape(taskID),
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
		return "", fmt.Errorf("Airflow task state response must be an object")
	}
	state, _ := payload["state"].(string)
	if strings.TrimSpace(state) == "" {
		return "unknown", nil
	}
	return state, nil
}
