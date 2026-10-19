package airflow

import (
	"context"
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

var dependencyRerunPolicy = clearPolicy{
	includeDownstream: true,
	includeFuture:     false,
	includePast:       false,
	includeUpstream:   false,
	onlyFailed:        false,
	onlyRunning:       false,
	resetDAGRuns:      true,
}

// PlanDependencyRerun returns a bounded non-failed downstream selection.
func PlanDependencyRerun(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	config Credentials,
	transport Transport,
	runState string,
) ([]prodsupport.RetryTaskReference, error) {
	if !terminalDAGRunState(runState) {
		return nil, fmt.Errorf(
			"dependency re-run blocked: DAG run %s has non-terminal state %s",
			batch.RunID,
			runState,
		)
	}
	planned, err := planClear(
		ctx,
		batch,
		dependencyRerunPolicy,
		config,
		transport,
	)
	if err != nil {
		return nil, err
	}
	for _, reference := range planned {
		if !missingTaskState(reference.State) &&
			!terminalTaskState(reference.State) {
			return nil, fmt.Errorf(
				"dependency re-run blocked: task %s in run %s has non-terminal state %s",
				reference.TaskID,
				reference.RunID,
				reference.State,
			)
		}
	}
	return planned, nil
}

// ExecuteDependencyRerun revalidates and clears one exact downstream selection.
func ExecuteDependencyRerun(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	approvalID string,
	config Credentials,
	transport Transport,
	runState string,
) ([]prodsupport.RetryTaskReference, error) {
	if strings.TrimSpace(approvalID) == "" {
		return nil, fmt.Errorf("Airflow clear execution requires an approval ID")
	}
	planned, err := PlanDependencyRerun(
		ctx,
		batch,
		config,
		transport,
		runState,
	)
	if err != nil {
		return nil, err
	}
	response, err := transport.Request(
		ctx,
		config,
		"POST",
		clearPath(batch.DAGID),
		clearPayload(batch, dependencyRerunPolicy, false),
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
	for index := range cleared {
		if missingTaskState(cleared[index].State) {
			cleared[index].State = "cleared"
		}
	}
	return cleared, nil
}

func missingTaskState(state string) bool {
	switch state {
	case "", "<nil>", "none", "unknown":
		return true
	default:
		return false
	}
}

func terminalTaskState(state string) bool {
	switch state {
	case "failed", "removed", "skipped", "success", "upstream_failed":
		return true
	default:
		return false
	}
}

func terminalDAGRunState(state string) bool {
	return state == "failed" || state == "success"
}
