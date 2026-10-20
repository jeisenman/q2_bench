package airflow

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// FetchTaskLog retrieves one exact task-attempt log without requiring a
// terminal Airflow failure value.
func (s *Source) FetchTaskLog(
	ctx context.Context,
	region prodsupport.Region,
	dagID string,
	runID string,
	taskID string,
	tryNumber int,
) (string, error) {
	for field, value := range map[string]string{
		"dag_id":  dagID,
		"run_id":  runID,
		"task_id": taskID,
	} {
		if strings.TrimSpace(value) == "" {
			return "", fmt.Errorf("%s must not be empty", field)
		}
	}
	if tryNumber < 1 {
		return "", fmt.Errorf("try_number must be positive")
	}
	config, err := s.configFor(region)
	if err != nil {
		return "", err
	}
	parts := []string{
		"dags", dagID, "dagRuns", runID, "taskInstances",
		taskID, "logs", strconv.Itoa(tryNumber),
	}
	path := "/api/v1"
	for _, part := range parts {
		path += "/" + url.PathEscape(part)
	}
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
	switch typed := response.(type) {
	case string:
		return typed, nil
	case map[string]any:
		if content, ok := typed["content"].(string); ok {
			return content, nil
		}
	}
	return "", fmt.Errorf("Airflow task log response must contain text content")
}
