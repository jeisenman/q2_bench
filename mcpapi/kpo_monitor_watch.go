package mcpapi

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/jeisenman/q2_bench/adapters/airflow"
	"github.com/jeisenman/q2_bench/adapters/kubernetes"
	"github.com/jeisenman/q2_bench/kpomonitor"
	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func (a *kpoMonitorAPI) watch(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input watchKPOMemoryInput,
) (*mcp.CallToolResult, watchKPOMemoryOutput, error) {
	region, err := kpoRegion(input.Region)
	if err != nil {
		return nil, watchKPOMemoryOutput{}, err
	}
	if err := validateKPOIdentity(input.DAGID, input.RunID, input.TaskID); err != nil {
		return nil, watchKPOMemoryOutput{}, err
	}
	if input.BaselineTryNumber < 1 {
		return nil, watchKPOMemoryOutput{}, fmt.Errorf(
			"baseline_try_number must be positive",
		)
	}
	interval, count, err := kpoPollBounds(
		input.PollIntervalSeconds,
		input.PollCount,
	)
	if err != nil {
		return nil, watchKPOMemoryOutput{}, err
	}
	history, err := validatedKPOHistory(input.History, input.BaselineTryNumber)
	if err != nil {
		return nil, watchKPOMemoryOutput{}, err
	}
	metadata, err := a.airflow.source.FetchTaskOperator(
		ctx,
		region,
		input.DAGID,
		input.TaskID,
	)
	if err != nil {
		return nil, watchKPOMemoryOutput{}, err
	}
	if !kpomonitor.SupportedOperator(metadata.OperatorName) {
		return nil, watchKPOMemoryOutput{}, fmt.Errorf(
			"operator %s is not supported; expected SparkSubmitOperator or KubernetesPodOperator",
			metadata.OperatorName,
		)
	}
	output := watchKPOMemoryOutput{
		Region:            input.Region,
		DAGID:             input.DAGID,
		RunID:             input.RunID,
		TaskID:            input.TaskID,
		OperatorName:      metadata.OperatorName,
		BaselineTryNumber: input.BaselineTryNumber,
		History:           history,
		Warnings:          []string{},
	}
	warnings := make(map[string]struct{})
	for index := 0; index < count; index++ {
		instance, readErr := a.airflow.source.GetTaskInstance(
			ctx,
			region,
			input.DAGID,
			input.RunID,
			input.TaskID,
		)
		if readErr != nil {
			return nil, watchKPOMemoryOutput{}, readErr
		}
		output.CurrentTryNumber = instance.TryNumber
		output.TaskState = instance.State
		output.RerunStarted = instance.TryNumber > input.BaselineTryNumber
		if output.RerunStarted {
			if err := a.sampleAttempt(ctx, region, instance, &output, warnings); err != nil {
				return nil, watchKPOMemoryOutput{}, err
			}
		} else {
			warnings["waiting for an Airflow attempt newer than the baseline"] = struct{}{}
		}
		output.Complete = output.RerunStarted && terminalTaskState(instance.State)
		if output.Complete || index == count-1 {
			break
		}
		if err := a.sleep(ctx, interval); err != nil {
			return nil, watchKPOMemoryOutput{}, err
		}
	}
	for warning := range warnings {
		output.Warnings = append(output.Warnings, warning)
	}
	sort.Strings(output.Warnings)
	output.Summary = kpomonitor.Summarize(output.History)
	output.Graph = kpomonitor.BuildGraph(output.History)
	return nil, output, nil
}

func (a *kpoMonitorAPI) sampleAttempt(
	ctx context.Context,
	region prodsupport.Region,
	instance airflow.TaskInstance,
	output *watchKPOMemoryOutput,
	warnings map[string]struct{},
) error {
	log, err := a.airflow.source.FetchTaskLog(
		ctx,
		region,
		instance.DAGID,
		instance.RunID,
		instance.TaskID,
		instance.TryNumber,
	)
	if err != nil {
		if !expectedPendingLog(err, instance.State) {
			return err
		}
		warnings["Airflow log is not available for the new attempt yet"] = struct{}{}
		return nil
	}
	reference, found := kpomonitor.PodReferenceFromLog(log, kpoNamespace)
	if !found {
		warnings["Airflow has not emitted the workload pod name yet"] = struct{}{}
		return nil
	}
	snapshot, err := a.kube.Snapshot(
		ctx,
		clusterContexts[region],
		reference.Namespace,
		reference.Name,
	)
	if err != nil {
		var notFound *kubernetes.PodNotFoundError
		if !errors.As(err, &notFound) {
			return err
		}
		warnings[notFound.Error()] = struct{}{}
		return nil
	}
	sample, err := kpomonitor.NewMemorySample(
		instance.State,
		instance.TryNumber,
		snapshot,
	)
	if err != nil {
		return err
	}
	output.History, err = kpomonitor.AppendHistory(output.History, sample)
	if err != nil {
		return err
	}
	output.DriverPod = snapshot.DriverPod
	output.ApplicationSelector = snapshot.ApplicationSelector
	for _, warning := range snapshot.Warnings {
		warnings[warning] = struct{}{}
	}
	return nil
}

func validatedKPOHistory(
	history []kpomonitor.MemorySample,
	baselineTryNumber int,
) ([]kpomonitor.MemorySample, error) {
	result, err := kpomonitor.AppendHistory(history)
	if err != nil {
		return nil, err
	}
	for _, sample := range result {
		if sample.TryNumber <= baselineTryNumber {
			return nil, fmt.Errorf(
				"history contains try_number %d that is not newer than baseline %d",
				sample.TryNumber,
				baselineTryNumber,
			)
		}
	}
	return result, nil
}

func kpoPollBounds(
	intervalSeconds int,
	count int,
) (time.Duration, int, error) {
	if intervalSeconds == 0 {
		intervalSeconds = defaultKPOPollIntervalSeconds
	}
	if count == 0 {
		count = defaultKPOPollCount
	}
	if intervalSeconds < minimumKPOPollIntervalSeconds ||
		intervalSeconds > maximumKPOPollIntervalSeconds {
		return 0, 0, fmt.Errorf(
			"poll_interval_seconds must be between %d and %d",
			minimumKPOPollIntervalSeconds,
			maximumKPOPollIntervalSeconds,
		)
	}
	if count < 1 || count > maximumKPOPollCount {
		return 0, 0, fmt.Errorf(
			"poll_count must be between 1 and %d",
			maximumKPOPollCount,
		)
	}
	if (count-1)*intervalSeconds > maximumKPOWatchSeconds {
		return 0, 0, fmt.Errorf(
			"one watch call must not exceed %d seconds",
			maximumKPOWatchSeconds,
		)
	}
	return time.Duration(intervalSeconds) * time.Second, count, nil
}

func expectedPendingLog(err error, state string) bool {
	var statusErr *airflow.HTTPStatusError
	return errors.As(err, &statusErr) &&
		statusErr.StatusCode == 404 &&
		!terminalTaskState(state)
}

func terminalTaskState(state string) bool {
	switch state {
	case "success", "failed", "skipped", "upstream_failed", "removed":
		return true
	default:
		return false
	}
}
