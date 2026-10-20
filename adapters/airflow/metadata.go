package airflow

import (
	"context"
	"fmt"
	"net/url"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// FetchTaskOperator retrieves the exact Airflow operator name.
func (s *Source) FetchTaskOperator(
	ctx context.Context,
	region prodsupport.Region,
	dagID string,
	taskID string,
) (prodsupport.AirflowTaskMetadata, error) {
	for field, value := range map[string]string{
		"dag_id":  dagID,
		"task_id": taskID,
	} {
		if strings.TrimSpace(value) == "" {
			return prodsupport.AirflowTaskMetadata{}, fmt.Errorf(
				"%s must not be empty",
				field,
			)
		}
	}
	config, err := s.configFor(region)
	if err != nil {
		return prodsupport.AirflowTaskMetadata{}, err
	}
	path := fmt.Sprintf(
		"/api/v1/dags/%s/tasks/%s",
		url.PathEscape(dagID),
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
		return prodsupport.AirflowTaskMetadata{}, err
	}
	payload, ok := response.(map[string]any)
	if !ok {
		return prodsupport.AirflowTaskMetadata{}, fmt.Errorf(
			"Airflow task metadata response must be an object",
		)
	}
	operator, _ := payload["operator_name"].(string)
	if operator == "" {
		if classRef, ok := payload["class_ref"].(map[string]any); ok {
			operator, _ = classRef["class_name"].(string)
		}
	}
	metadata := prodsupport.AirflowTaskMetadata{
		DAGID:        dagID,
		TaskID:       taskID,
		OperatorName: operator,
	}
	if err := metadata.Validate(); err != nil {
		return prodsupport.AirflowTaskMetadata{}, fmt.Errorf(
			"Airflow task metadata response is missing operator_name",
		)
	}
	return metadata, nil
}
