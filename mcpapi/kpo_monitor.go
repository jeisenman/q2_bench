package mcpapi

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/jeisenman/q2_bench/adapters/kubernetes"
	"github.com/jeisenman/q2_bench/kpomonitor"
	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	defaultKPOPollIntervalSeconds = 15
	defaultKPOPollCount           = 4
	minimumKPOPollIntervalSeconds = 5
	maximumKPOPollIntervalSeconds = 60
	maximumKPOPollCount           = 20
	maximumKPOWatchSeconds        = 300
	kpoNamespace                  = "scheduler"
)

var kpoValidationURLs = []string{
	"https://airflow-us01.precisionlender.com/taskinstance/list/",
	"https://airflow-ca02.precisionlender.com/taskinstance/list/",
}

type kpoSnapshotSource interface {
	Preflight(
		context.Context,
		string,
		string,
	) error
	Snapshot(
		context.Context,
		string,
		string,
		string,
	) (kpomonitor.ApplicationSnapshot, error)
}

type kpoMonitorAPI struct {
	airflow *airflowAPI
	kube    kpoSnapshotSource
	sleep   func(context.Context, time.Duration) error
}

type prepareKPOMemoryProfileInput struct {
	Region string `json:"region"`
	DAGID  string `json:"dag_id"`
	RunID  string `json:"run_id"`
	TaskID string `json:"task_id"`
}

type prepareKPOMemoryProfileOutput struct {
	RetryCandidate    prodsupport.RetryCandidate `json:"retry_candidate"`
	ValidationURLs    []string                   `json:"validation_urls"`
	Direction         string                     `json:"direction"`
	BaselineTryNumber int                        `json:"baseline_try_number"`
	OperatorName      string                     `json:"operator_name"`
	ApprovalRequired  bool                       `json:"approval_required"`
	WatchInput        kpoMemoryWatchTemplate     `json:"watch_input"`
}

type kpoMemoryWatchTemplate struct {
	Region              string `json:"region"`
	DAGID               string `json:"dag_id"`
	RunID               string `json:"run_id"`
	TaskID              string `json:"task_id"`
	BaselineTryNumber   int    `json:"baseline_try_number"`
	PollIntervalSeconds int    `json:"poll_interval_seconds"`
	PollCount           int    `json:"poll_count"`
}

type watchKPOMemoryInput struct {
	Region              string                    `json:"region"`
	DAGID               string                    `json:"dag_id"`
	RunID               string                    `json:"run_id"`
	TaskID              string                    `json:"task_id"`
	BaselineTryNumber   int                       `json:"baseline_try_number"`
	PollIntervalSeconds int                       `json:"poll_interval_seconds,omitempty"`
	PollCount           int                       `json:"poll_count,omitempty"`
	History             []kpomonitor.MemorySample `json:"history,omitempty"`
}

type watchKPOMemoryOutput struct {
	Region              string                    `json:"region"`
	DAGID               string                    `json:"dag_id"`
	RunID               string                    `json:"run_id"`
	TaskID              string                    `json:"task_id"`
	OperatorName        string                    `json:"operator_name"`
	BaselineTryNumber   int                       `json:"baseline_try_number"`
	CurrentTryNumber    int                       `json:"current_try_number"`
	TaskState           string                    `json:"task_state"`
	RerunStarted        bool                      `json:"rerun_started"`
	Complete            bool                      `json:"complete"`
	DriverPod           string                    `json:"driver_pod,omitempty"`
	ApplicationSelector string                    `json:"application_selector,omitempty"`
	History             []kpomonitor.MemorySample `json:"history"`
	Summary             kpomonitor.ProfileSummary `json:"summary"`
	Graph               kpomonitor.MemoryGraph    `json:"graph"`
	Warnings            []string                  `json:"warnings"`
}

func registerKPOMonitor(server *mcp.Server, airflowAPI *airflowAPI) error {
	prepareSchema, watchSchema, err := kpoMonitorSchemas()
	if err != nil {
		return fmt.Errorf("register KPO memory monitor: %w", err)
	}
	api := &kpoMonitorAPI{
		airflow: airflowAPI,
		kube:    kubernetes.NewSource(nil),
		sleep:   kpoSleepContext,
	}
	mcp.AddTool(server, &mcp.Tool{
		Name: "prepare_kpo_memory_profile",
		Description: "Validate one exact failed Airflow task and return the approval-gated " +
			"retry candidate plus memory-watch input.",
		InputSchema: prepareSchema,
		Annotations: liveReadOnlyAnnotations(),
	}, api.prepare)
	mcp.AddTool(server, &mcp.Tool{
		Name: "watch_kpo_task_memory",
		Description: "Poll one approved Airflow rerun, map its Spark or Kubernetes pod, " +
			"and return bounded driver/executor memory history and graph data.",
		InputSchema: watchSchema,
		Annotations: liveReadOnlyAnnotations(),
	}, api.watch)
	return nil
}

func (a *kpoMonitorAPI) prepare(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input prepareKPOMemoryProfileInput,
) (*mcp.CallToolResult, prepareKPOMemoryProfileOutput, error) {
	region, err := kpoRegion(input.Region)
	if err != nil {
		return nil, prepareKPOMemoryProfileOutput{}, err
	}
	if err := validateKPOIdentity(input.DAGID, input.RunID, input.TaskID); err != nil {
		return nil, prepareKPOMemoryProfileOutput{}, err
	}
	status, err := a.airflow.source.GetDAGStatus(ctx, region, input.DAGID)
	if err != nil {
		return nil, prepareKPOMemoryProfileOutput{}, err
	}
	if !status.Exists {
		return nil, prepareKPOMemoryProfileOutput{}, fmt.Errorf(
			"Airflow DAG %s does not exist",
			input.DAGID,
		)
	}
	if status.IsPaused {
		return nil, prepareKPOMemoryProfileOutput{}, fmt.Errorf(
			"Airflow DAG %s is paused",
			input.DAGID,
		)
	}
	instance, err := a.airflow.source.GetTaskInstance(
		ctx,
		region,
		input.DAGID,
		input.RunID,
		input.TaskID,
	)
	if err != nil {
		return nil, prepareKPOMemoryProfileOutput{}, err
	}
	if instance.State != "failed" {
		return nil, prepareKPOMemoryProfileOutput{}, fmt.Errorf(
			"Airflow task must currently be failed for an approval-gated retry; state is %s",
			instance.State,
		)
	}
	if instance.TryNumber < 1 {
		return nil, prepareKPOMemoryProfileOutput{}, fmt.Errorf(
			"Airflow task try_number is unavailable",
		)
	}
	metadata, err := a.airflow.source.FetchTaskOperator(
		ctx,
		region,
		input.DAGID,
		input.TaskID,
	)
	if err != nil {
		return nil, prepareKPOMemoryProfileOutput{}, err
	}
	if !kpomonitor.SupportedOperator(metadata.OperatorName) {
		return nil, prepareKPOMemoryProfileOutput{}, fmt.Errorf(
			"operator %s is not supported; expected SparkSubmitOperator or KubernetesPodOperator",
			metadata.OperatorName,
		)
	}
	if err := a.kube.Preflight(
		ctx,
		clusterContexts[region],
		kpoNamespace,
	); err != nil {
		return nil, prepareKPOMemoryProfileOutput{}, fmt.Errorf(
			"Kubernetes memory monitor preflight: %w",
			err,
		)
	}
	candidate := prodsupport.RetryCandidate{
		Number: 1,
		Region: region,
		DAGID:  input.DAGID,
		RunID:  input.RunID,
		TaskID: input.TaskID,
		Label:  prodsupport.JobLabel(input.TaskID),
	}
	return nil, prepareKPOMemoryProfileOutput{
		RetryCandidate:    candidate,
		ValidationURLs:    append([]string(nil), kpoValidationURLs...),
		Direction:         "retry 1",
		BaselineTryNumber: instance.TryNumber,
		OperatorName:      metadata.OperatorName,
		ApprovalRequired:  true,
		WatchInput: kpoMemoryWatchTemplate{
			Region:              input.Region,
			DAGID:               input.DAGID,
			RunID:               input.RunID,
			TaskID:              input.TaskID,
			BaselineTryNumber:   instance.TryNumber,
			PollIntervalSeconds: defaultKPOPollIntervalSeconds,
			PollCount:           defaultKPOPollCount,
		},
	}, nil
}

func kpoRegion(value string) (prodsupport.Region, error) {
	region := prodsupport.Region(value)
	if region != prodsupport.US01 && region != prodsupport.CA02 {
		return "", fmt.Errorf("region must be US-01 or CA-02")
	}
	return region, nil
}

func validateKPOIdentity(dagID string, runID string, taskID string) error {
	for field, value := range map[string]string{
		"dag_id":  dagID,
		"run_id":  runID,
		"task_id": taskID,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", field)
		}
	}
	return nil
}

func liveReadOnlyAnnotations() *mcp.ToolAnnotations {
	destructive := false
	openWorld := true
	return &mcp.ToolAnnotations{
		DestructiveHint: &destructive,
		IdempotentHint:  false,
		OpenWorldHint:   &openWorld,
		ReadOnlyHint:    true,
	}
}

func kpoMonitorSchemas() (*jsonschema.Schema, *jsonschema.Schema, error) {
	prepare, err := jsonschema.For[prepareKPOMemoryProfileInput](nil)
	if err != nil {
		return nil, nil, fmt.Errorf("build prepare input schema: %w", err)
	}
	watch, err := jsonschema.For[watchKPOMemoryInput](nil)
	if err != nil {
		return nil, nil, fmt.Errorf("build watch input schema: %w", err)
	}
	for _, schema := range []*jsonschema.Schema{prepare, watch} {
		region, propertyErr := kpoSchemaProperty(schema, "region")
		if propertyErr != nil {
			return nil, nil, propertyErr
		}
		region.Enum = []any{"US-01", "CA-02"}
	}
	minimumOne := float64(1)
	minimumInterval := float64(minimumKPOPollIntervalSeconds)
	maximumInterval := float64(maximumKPOPollIntervalSeconds)
	maximumCount := float64(maximumKPOPollCount)
	baseline, err := kpoSchemaProperty(watch, "baseline_try_number")
	if err != nil {
		return nil, nil, err
	}
	baseline.Minimum = &minimumOne
	interval, err := kpoSchemaProperty(watch, "poll_interval_seconds")
	if err != nil {
		return nil, nil, err
	}
	interval.Minimum = &minimumInterval
	interval.Maximum = &maximumInterval
	count, err := kpoSchemaProperty(watch, "poll_count")
	if err != nil {
		return nil, nil, err
	}
	count.Minimum = &minimumOne
	count.Maximum = &maximumCount
	history, err := kpoSchemaProperty(watch, "history")
	if err != nil {
		return nil, nil, err
	}
	maximumHistory := kpomonitor.MaxHistorySamples
	history.MaxItems = &maximumHistory
	return prepare, watch, nil
}

func kpoSleepContext(ctx context.Context, duration time.Duration) error {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
