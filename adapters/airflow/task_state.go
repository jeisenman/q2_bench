package airflow

import (
	"context"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// TaskInstance is the current state and attempt identity of an Airflow task.
type TaskInstance struct {
	Region    prodsupport.Region
	DAGID     string
	RunID     string
	TaskID    string
	State     string
	TryNumber int
	StartAt   *time.Time
	EndAt     *time.Time
}

// GetTaskState reads the current state of one exact Airflow task instance.
func (s *Source) GetTaskState(
	ctx context.Context,
	region prodsupport.Region,
	dagID, runID, taskID string,
) (string, error) {
	instance, err := s.GetTaskInstance(ctx, region, dagID, runID, taskID)
	if err != nil {
		return "", err
	}
	return instance.State, nil
}

// GetTaskInstance reads current state, attempt, and timestamps.
func (s *Source) GetTaskInstance(
	ctx context.Context,
	region prodsupport.Region,
	dagID, runID, taskID string,
) (TaskInstance, error) {
	for name, value := range map[string]string{
		"dag_id": dagID, "run_id": runID, "task_id": taskID,
	} {
		if strings.TrimSpace(value) == "" {
			return TaskInstance{}, fmt.Errorf("%s must not be empty", name)
		}
	}
	config, err := s.configFor(region)
	if err != nil {
		return TaskInstance{}, err
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
		return TaskInstance{}, err
	}
	payload, ok := response.(map[string]any)
	if !ok {
		return TaskInstance{}, fmt.Errorf("Airflow task instance response must be an object")
	}
	state, _ := payload["state"].(string)
	if strings.TrimSpace(state) == "" {
		state = "unknown"
	}
	tryNumber, ok := integer(payload["try_number"])
	if payload["try_number"] == nil {
		tryNumber = 0
	} else if !ok || tryNumber < 0 {
		return TaskInstance{}, fmt.Errorf(
			"Airflow task instance response has invalid try_number",
		)
	}
	startAt, err := optionalTaskTimestamp(payload["start_date"])
	if err != nil {
		return TaskInstance{}, fmt.Errorf("Airflow task start_date: %w", err)
	}
	endAt, err := optionalTaskTimestamp(payload["end_date"])
	if err != nil {
		return TaskInstance{}, fmt.Errorf("Airflow task end_date: %w", err)
	}
	return TaskInstance{
		Region:    region,
		DAGID:     dagID,
		RunID:     runID,
		TaskID:    taskID,
		State:     state,
		TryNumber: tryNumber,
		StartAt:   startAt,
		EndAt:     endAt,
	}, nil
}

func optionalTaskTimestamp(value any) (*time.Time, error) {
	if value == nil {
		return nil, nil
	}
	parsed, err := parseTimestamp(value)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}
