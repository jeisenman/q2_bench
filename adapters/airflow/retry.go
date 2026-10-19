package airflow

import (
	"context"
	"fmt"
	"net/url"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

type clearPolicy struct {
	includeDownstream bool
	includeFuture     bool
	includePast       bool
	includeUpstream   bool
	onlyFailed        bool
	onlyRunning       bool
	resetDAGRuns      bool
}

var failedRetryPolicy = clearPolicy{
	includeDownstream: true,
	includeFuture:     false,
	includePast:       false,
	includeUpstream:   false,
	onlyFailed:        true,
	onlyRunning:       false,
	resetDAGRuns:      true,
}

// PlanRetry returns Airflow's validated dry-run task selection.
func PlanRetry(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	config Credentials,
	transport Transport,
) ([]prodsupport.RetryTaskReference, error) {
	return planClear(ctx, batch, failedRetryPolicy, config, transport)
}

func planClear(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	policy clearPolicy,
	config Credentials,
	transport Transport,
) ([]prodsupport.RetryTaskReference, error) {
	response, err := transport.Request(
		ctx,
		config,
		"POST",
		clearPath(batch.DAGID),
		clearPayload(batch, policy, true),
	)
	if err != nil {
		return nil, err
	}
	return references(response, batch)
}

// ExecuteRetry revalidates, clears approved tasks and downstream failures, and
// reads every cleared task state.
func ExecuteRetry(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	approvalID string,
	config Credentials,
	transport Transport,
	stateReader func(context.Context, string) (any, error),
) ([]prodsupport.RetryTaskReference, error) {
	return executeClear(
		ctx,
		batch,
		approvalID,
		failedRetryPolicy,
		config,
		transport,
		stateReader,
		PlanRetry,
	)
}

type planClearFunc func(
	context.Context,
	prodsupport.RetryBatch,
	Credentials,
	Transport,
) ([]prodsupport.RetryTaskReference, error)

func executeClear(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	approvalID string,
	policy clearPolicy,
	config Credentials,
	transport Transport,
	stateReader func(context.Context, string) (any, error),
	plan planClearFunc,
) ([]prodsupport.RetryTaskReference, error) {
	if strings.TrimSpace(approvalID) == "" {
		return nil, fmt.Errorf("Airflow clear execution requires an approval ID")
	}
	planned, err := plan(ctx, batch, config, transport)
	if err != nil {
		return nil, err
	}
	response, err := transport.Request(
		ctx,
		config,
		"POST",
		clearPath(batch.DAGID),
		clearPayload(batch, policy, false),
	)
	if err != nil {
		return nil, err
	}
	cleared, err := references(response, batch)
	if err != nil {
		return nil, err
	}
	if !sameTaskIDs(planned, cleared) {
		return nil, fmt.Errorf(
			"Airflow clear response did not match the dry-run task set",
		)
	}
	states := make([]prodsupport.RetryTaskReference, len(cleared))
	for index, reference := range cleared {
		state, err := stateReader(ctx, reference.TaskID)
		if err != nil {
			return nil, err
		}
		payload, ok := state.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("Airflow retry state response must be an object")
		}
		reference.State = fmt.Sprint(payload["state"])
		if reference.State == "<nil>" {
			reference.State = "unknown"
		}
		states[index] = reference
	}
	return states, nil
}

func sameTaskIDs(
	left []prodsupport.RetryTaskReference,
	right []prodsupport.RetryTaskReference,
) bool {
	if len(left) != len(right) {
		return false
	}
	leftIDs := make(map[string]struct{}, len(left))
	for _, reference := range left {
		leftIDs[reference.TaskID] = struct{}{}
	}
	for _, reference := range right {
		if _, exists := leftIDs[reference.TaskID]; !exists {
			return false
		}
	}
	return true
}

func clearPath(dagID string) string {
	return "/api/v1/dags/" + url.PathEscape(dagID) + "/clearTaskInstances"
}

func clearPayload(
	batch prodsupport.RetryBatch,
	policy clearPolicy,
	dryRun bool,
) map[string]any {
	return map[string]any{
		"dag_run_id": batch.RunID, "dry_run": dryRun,
		"include_downstream": policy.includeDownstream,
		"include_future":     policy.includeFuture,
		"include_past":       policy.includePast,
		"include_upstream":   policy.includeUpstream,
		"only_failed":        policy.onlyFailed,
		"only_running":       policy.onlyRunning,
		"reset_dag_runs":     policy.resetDAGRuns,
		"task_ids":           append([]string(nil), batch.TaskIDs...),
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
	orderedIDs := make([]string, 0, len(rawItems))
	for _, raw := range rawItems {
		item, ok := raw.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("Airflow retry response contains an invalid task instance")
		}
		if fmt.Sprint(item["dag_id"]) != batch.DAGID ||
			fmt.Sprint(item["dag_run_id"]) != batch.RunID {
			return nil, fmt.Errorf(
				"Airflow retry response contained a task from another DAG run",
			)
		}
		taskID := fmt.Sprint(item["task_id"])
		if taskID == "" || taskID == "<nil>" {
			return nil, fmt.Errorf("Airflow retry response contains an empty task ID")
		}
		if _, exists := items[taskID]; exists {
			return nil, fmt.Errorf(
				"Airflow retry response contains duplicate task %s",
				taskID,
			)
		}
		items[taskID] = item
		orderedIDs = append(orderedIDs, taskID)
	}
	for _, taskID := range batch.TaskIDs {
		if _, exists := items[taskID]; exists {
			continue
		}
		return nil, fmt.Errorf(
			"Airflow retry response did not include approved task %s",
			taskID,
		)
	}
	sort.Strings(orderedIDs)
	result := make([]prodsupport.RetryTaskReference, len(orderedIDs))
	for index, taskID := range orderedIDs {
		result[index] = prodsupport.RetryTaskReference{
			Region: batch.Region, DAGID: batch.DAGID, RunID: batch.RunID,
			TaskID: taskID, State: fmt.Sprint(items[taskID]["state"]),
		}
	}
	return result, nil
}
