package mcpapi

import (
	"context"
	"fmt"
	"time"

	"github.com/jeisenman/q2_bench/adapters/airflow"
	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type airflowAPI struct {
	source *airflow.Source
}

type listFailuresInput struct {
	Since  string `json:"since"`
	Region string `json:"region,omitempty"`
}

type failureInput struct {
	Failure failurePayload `json:"failure"`
}

type successInput struct {
	Failure failurePayload `json:"failure"`
	StartAt string         `json:"start_at"`
	EndAt   string         `json:"end_at"`
}

type failurePayload struct {
	Region    string `json:"region"`
	DAGID     string `json:"dag_id"`
	RunID     string `json:"run_id"`
	TaskID    string `json:"task_id"`
	StartAt   string `json:"start_at"`
	EndAt     string `json:"end_at"`
	TryNumber int    `json:"try_number"`
}

func registerAirflow(server *mcp.Server, config Config) error {
	api, err := newAirflowAPI(config.ConfigurationPath)
	if err != nil {
		return err
	}
	addAirflowTools(server, api)
	return nil
}

func newAirflowAPI(configurationPath string) (*airflowAPI, error) {
	if configurationPath == "" {
		configurationPath = "configurations.yaml"
	}
	us, err := airflow.LoadConnection(configurationPath, airflow.ProdUS, nil)
	if err != nil {
		return nil, err
	}
	ca, err := airflow.LoadConnection(configurationPath, airflow.ProdCA, nil)
	if err != nil {
		return nil, err
	}
	source := airflow.NewSource([]airflow.RegionConfig{
		{Region: prodsupport.US01, Credentials: us},
		{Region: prodsupport.CA02, Credentials: ca},
	}, nil)
	return &airflowAPI{source: source}, nil
}

func addAirflowTools(server *mcp.Server, api *airflowAPI) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_failed_task_instances",
		Description: "List failed Airflow task instances ending after a UTC cutoff.",
	}, api.listFailures)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_task_log",
		Description: "Read the exact Airflow log for one task instance and attempt.",
	}, api.getTaskLog)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "has_task_success",
		Description: "Check for a same-DAG same-task success in a bounded window.",
	}, api.hasTaskSuccess)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_task_metadata",
		Description: "Read exact Airflow task operator metadata for workload routing.",
	}, api.getTaskMetadata)
}

func (a *airflowAPI) listFailures(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input listFailuresInput,
) (*mcp.CallToolResult, map[string]any, error) {
	since, err := time.Parse(time.RFC3339, input.Since)
	if err != nil {
		return nil, nil, fmt.Errorf("since must be RFC3339 with a timezone: %w", err)
	}
	var failures []prodsupport.AirflowFailure
	if input.Region == "" {
		failures, err = a.source.DiscoverFailures(ctx, since)
	} else {
		failures, err = a.source.DiscoverRegionFailures(
			ctx, prodsupport.Region(input.Region), since,
		)
	}
	if err != nil {
		return nil, nil, err
	}
	values := make([]failurePayload, len(failures))
	for index, failure := range failures {
		values[index] = payloadFromFailure(failure)
	}
	return nil, map[string]any{"failures": values, "count": len(values)}, nil
}

func (a *airflowAPI) hasTaskSuccess(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input successInput,
) (*mcp.CallToolResult, map[string]any, error) {
	failure, err := input.Failure.failure()
	if err != nil {
		return nil, nil, err
	}
	startAt, err := time.Parse(time.RFC3339Nano, input.StartAt)
	if err != nil {
		return nil, nil, fmt.Errorf("invalid start_at: %w", err)
	}
	endAt, err := time.Parse(time.RFC3339Nano, input.EndAt)
	if err != nil {
		return nil, nil, fmt.Errorf("invalid end_at: %w", err)
	}
	recovered, err := a.source.HasSuccessWithin(ctx, failure, startAt, endAt)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"failure_id": failure.FailureID(), "has_success": recovered,
	}, nil
}

func (a *airflowAPI) getTaskLog(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input failureInput,
) (*mcp.CallToolResult, map[string]any, error) {
	failure, err := input.Failure.failure()
	if err != nil {
		return nil, nil, err
	}
	log, err := a.source.FetchLog(ctx, failure)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{"failure_id": failure.FailureID(), "log": log}, nil
}

func (a *airflowAPI) getTaskMetadata(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input failureInput,
) (*mcp.CallToolResult, map[string]any, error) {
	failure, err := input.Failure.failure()
	if err != nil {
		return nil, nil, err
	}
	metadata, err := a.source.FetchTaskMetadata(ctx, failure)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"dag_id": metadata.DAGID, "task_id": metadata.TaskID,
		"operator_name": metadata.OperatorName,
	}, nil
}

func (p failurePayload) failure() (prodsupport.AirflowFailure, error) {
	startAt, err := time.Parse(time.RFC3339Nano, p.StartAt)
	if err != nil {
		return prodsupport.AirflowFailure{}, fmt.Errorf("invalid start_at: %w", err)
	}
	endAt, err := time.Parse(time.RFC3339Nano, p.EndAt)
	if err != nil {
		return prodsupport.AirflowFailure{}, fmt.Errorf("invalid end_at: %w", err)
	}
	value := prodsupport.AirflowFailure{
		Region: prodsupport.Region(p.Region), DAGID: p.DAGID, RunID: p.RunID,
		TaskID: p.TaskID, StartAt: startAt, EndAt: endAt, TryNumber: p.TryNumber,
	}
	return value, value.Validate()
}

func payloadFromFailure(failure prodsupport.AirflowFailure) failurePayload {
	return failurePayload{
		Region: string(failure.Region), DAGID: failure.DAGID, RunID: failure.RunID,
		TaskID: failure.TaskID, StartAt: failure.StartAt.Format(time.RFC3339Nano),
		EndAt: failure.EndAt.Format(time.RFC3339Nano), TryNumber: failure.TryNumber,
	}
}
