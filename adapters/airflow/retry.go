package airflow

import (
	"context"
	"fmt"
	"net/url"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// PlanRetry returns Airflow's validated dry-run task selection.
func PlanRetry(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	config Credentials,
	transport Transport,
) ([]prodsupport.RetryTaskReference, error) {
	response, err := transport.Request(
		ctx,
		config,
		"POST",
		clearPath(batch.DAGID),
		retryPayload(batch, true),
	)
	if err != nil {
		return nil, err
	}
	return references(response, batch)
}

// ExecuteRetry revalidates, clears exact tasks, and reads their states.
func ExecuteRetry(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	approvalID string,
	config Credentials,
	transport Transport,
	stateReader func(context.Context, string) (any, error),
) ([]prodsupport.RetryTaskReference, error) {
	if strings.TrimSpace(approvalID) == "" {
		return nil, fmt.Errorf("Airflow retry execution requires an approval ID")
	}
	if _, err := PlanRetry(ctx, batch, config, transport); err != nil {
		return nil, err
	}
	response, err := transport.Request(
		ctx,
		config,
		"POST",
		clearPath(batch.DAGID),
		retryPayload(batch, false),
	)
	if err != nil {
		return nil, err
	}
	if _, err := references(response, batch); err != nil {
		return nil, err
	}
	states := make([]prodsupport.RetryTaskReference, len(batch.TaskIDs))
	for index, taskID := range batch.TaskIDs {
		state, err := stateReader(ctx, taskID)
		if err != nil {
			return nil, err
		}
		payload, ok := state.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("Airflow retry state response must be an object")
		}
		states[index] = prodsupport.RetryTaskReference{
			Region: batch.Region, DAGID: batch.DAGID, RunID: batch.RunID,
			TaskID: taskID, State: fmt.Sprint(payload["state"]),
		}
		if states[index].State == "<nil>" {
			states[index].State = "unknown"
		}
	}
	return states, nil
}

func clearPath(dagID string) string {
	return "/api/v1/dags/" + url.PathEscape(dagID) + "/clearTaskInstances"
}

func retryPayload(batch prodsupport.RetryBatch, dryRun bool) map[string]any {
	return map[string]any{
		"dag_run_id": batch.RunID, "dry_run": dryRun,
		"include_downstream": true, "include_future": false, "include_past": false,
		"include_upstream": false, "only_failed": true, "only_running": false,
		"reset_dag_runs": true, "task_ids": append([]string(nil), batch.TaskIDs...),
	}
}

func references(
	response any,
	batch prodsupport.RetryBatch,
) ([]prodsupport.RetryTaskReference, error) {
	payload, ok := response.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("Airflow retry response must contain task_instances")
	}
	rawItems, ok := payload["task_instances"].([]any)
	if !ok {
		return nil, fmt.Errorf("Airflow retry response must contain task_instances")
	}
	items := make(map[string]map[string]any)
	for _, raw := range rawItems {
		item, ok := raw.(map[string]any)
		if !ok || fmt.Sprint(item["dag_id"]) != batch.DAGID ||
			fmt.Sprint(item["dag_run_id"]) != batch.RunID {
			continue
		}
		items[fmt.Sprint(item["task_id"])] = item
	}
	if len(items) != len(batch.TaskIDs) || len(rawItems) != len(batch.TaskIDs) {
		return nil, fmt.Errorf("Airflow retry response did not match the exact request")
	}
	result := make([]prodsupport.RetryTaskReference, len(batch.TaskIDs))
	for index, taskID := range batch.TaskIDs {
		item, exists := items[taskID]
		if !exists {
			return nil, fmt.Errorf("Airflow retry response did not match the exact request")
		}
		result[index] = prodsupport.RetryTaskReference{
			Region: batch.Region, DAGID: batch.DAGID, RunID: batch.RunID,
			TaskID: taskID, State: fmt.Sprint(item["state"]),
		}
	}
	return result, nil
}
