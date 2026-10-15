package mcpapi

import (
	"context"
	"fmt"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

func (a *prodSupportAPI) preflightFollowUp(
	ctx context.Context,
	batches []prodsupport.RetryBatch,
) error {
	if a.airflow == nil || a.airflow.source == nil {
		return fmt.Errorf("retry blocked: Airflow guards must be configured")
	}
	dags := make(map[string]prodsupport.RetryBatch)
	for _, batch := range batches {
		dags[string(batch.Region)+"\x00"+batch.DAGID] = batch
	}
	for _, batch := range orderedDAGBatches(batches, dags) {
		status, err := a.airflow.source.GetDAGStatus(
			ctx,
			batch.Region,
			batch.DAGID,
		)
		if err != nil {
			return fmt.Errorf(
				"retry blocked: %s DAG %s status check failed: %w",
				batch.Region,
				batch.DAGID,
				err,
			)
		}
		if !status.Exists {
			return fmt.Errorf(
				"retry blocked: %s DAG %s does not exist",
				batch.Region,
				batch.DAGID,
			)
		}
		if status.IsPaused {
			return fmt.Errorf(
				"retry blocked: %s DAG %s is paused",
				batch.Region,
				batch.DAGID,
			)
		}
	}
	return nil
}

func orderedDAGBatches(
	batches []prodsupport.RetryBatch,
	unique map[string]prodsupport.RetryBatch,
) []prodsupport.RetryBatch {
	ordered := make([]prodsupport.RetryBatch, 0, len(unique))
	seen := make(map[string]struct{}, len(unique))
	for _, batch := range batches {
		key := string(batch.Region) + "\x00" + batch.DAGID
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		ordered = append(ordered, unique[key])
	}
	return ordered
}
