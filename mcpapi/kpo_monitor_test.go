package mcpapi

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/jeisenman/q2_bench/adapters/airflow"
	"github.com/jeisenman/q2_bench/kpomonitor"
	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	testKPODAG  = "l3-main-b441897e-a525-4546-b68c-3f6820de847c"
	testKPORun  = "manual__2026-10-13T05:00:00+00:00"
	testKPOTask = "high_quality_core_account_financial_statements." +
		"high_quality_core_account_financial_statements"
	testKPODriver = "high-quality-core-account-financial-statements-" +
		"2f69309e-723e-42cf-9375-4020e6f44208-driver"
)

type kpoMonitorTransport struct {
	state    string
	try      int
	operator string
	paused   bool
	log      string
}

func (t *kpoMonitorTransport) Request(
	_ context.Context,
	_ airflow.Credentials,
	method string,
	path string,
	_ map[string]any,
) (any, error) {
	if method != "GET" {
		return nil, errors.New("unexpected Airflow mutation")
	}
	switch {
	case path == "/api/v1/dags/"+testKPODAG:
		return map[string]any{"is_paused": t.paused}, nil
	case strings.Contains(path, "/taskInstances/") &&
		!strings.Contains(path, "/logs/"):
		return map[string]any{
			"state":      t.state,
			"try_number": t.try,
			"start_date": "2026-10-15T19:00:00Z",
			"end_date":   nil,
		}, nil
	case strings.Contains(path, "/tasks/"):
		return map[string]any{"operator_name": t.operator}, nil
	case strings.Contains(path, "/logs/"):
		return t.log, nil
	default:
		return nil, errors.New("unexpected Airflow path: " + path)
	}
}

type kpoSnapshotStub struct {
	snapshot       kpomonitor.ApplicationSnapshot
	preflightErr   error
	preflightCalls int
	calls          int
	context        string
	namespace      string
	pod            string
}

func (s *kpoSnapshotStub) Preflight(
	_ context.Context,
	clusterContext string,
	namespace string,
) error {
	s.preflightCalls++
	s.context = clusterContext
	s.namespace = namespace
	return s.preflightErr
}

func (s *kpoSnapshotStub) Snapshot(
	_ context.Context,
	clusterContext string,
	namespace string,
	pod string,
) (kpomonitor.ApplicationSnapshot, error) {
	s.calls++
	s.context = clusterContext
	s.namespace = namespace
	s.pod = pod
	return s.snapshot, nil
}

func TestPrepareKPOMemoryProfileReturnsExactApprovalInputs(t *testing.T) {
	t.Parallel()
	kube := &kpoSnapshotStub{}
	api := newTestKPOMonitorAPI(&kpoMonitorTransport{
		state:    "failed",
		try:      6,
		operator: "SparkSubmitOperator",
	}, kube)
	_, output, err := api.prepare(
		context.Background(),
		nil,
		prepareKPOMemoryProfileInput{
			Region: "US-01",
			DAGID:  testKPODAG,
			RunID:  testKPORun,
			TaskID: testKPOTask,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if output.BaselineTryNumber != 6 ||
		output.RetryCandidate.Region != prodsupport.US01 ||
		output.RetryCandidate.DAGID != testKPODAG ||
		output.RetryCandidate.RunID != testKPORun ||
		output.RetryCandidate.TaskID != testKPOTask ||
		output.Direction != "retry 1" ||
		!output.ApprovalRequired {
		t.Fatalf("output = %#v", output)
	}
	if !reflect.DeepEqual(output.ValidationURLs, kpoValidationURLs) {
		t.Fatalf("validation URLs = %#v", output.ValidationURLs)
	}
	if kube.preflightCalls != 1 || kube.context != "l3-us01" ||
		kube.namespace != "scheduler" {
		t.Fatalf("Kubernetes preflight = %#v", kube)
	}
}

func TestPrepareKPOMemoryProfileRejectsNonFailedTask(t *testing.T) {
	t.Parallel()
	api := newTestKPOMonitorAPI(&kpoMonitorTransport{
		state:    "success",
		try:      6,
		operator: "SparkSubmitOperator",
	}, &kpoSnapshotStub{})
	_, _, err := api.prepare(
		context.Background(),
		nil,
		prepareKPOMemoryProfileInput{
			Region: "US-01",
			DAGID:  testKPODAG,
			RunID:  testKPORun,
			TaskID: testKPOTask,
		},
	)
	if err == nil || !strings.Contains(err.Error(), "must currently be failed") {
		t.Fatalf("error = %v", err)
	}
}

func TestPrepareKPOMemoryProfileRequiresKubernetesAccess(t *testing.T) {
	t.Parallel()
	api := newTestKPOMonitorAPI(&kpoMonitorTransport{
		state:    "failed",
		try:      6,
		operator: "SparkSubmitOperator",
	}, &kpoSnapshotStub{preflightErr: errors.New("metrics denied")})
	_, _, err := api.prepare(
		context.Background(),
		nil,
		prepareKPOMemoryProfileInput{
			Region: "US-01",
			DAGID:  testKPODAG,
			RunID:  testKPORun,
			TaskID: testKPOTask,
		},
	)
	if err == nil || !strings.Contains(err.Error(), "metrics denied") {
		t.Fatalf("error = %v", err)
	}
}

func TestWatchKPOMemoryMapsSparkApplicationAndBuildsGraph(t *testing.T) {
	t.Parallel()
	transport := &kpoMonitorTransport{
		state:    "running",
		try:      7,
		operator: "SparkSubmitOperator",
		log:      "Path to spark driver pod: scheduler:" + testKPODriver,
	}
	kube := &kpoSnapshotStub{snapshot: kpomonitor.ApplicationSnapshot{
		ObservedAt:          "2026-10-15T19:01:00Z",
		DriverPod:           testKPODriver,
		ApplicationSelector: "spark-123",
		Pods: []kpomonitor.PodMemorySample{
			{
				Name:               testKPODriver,
				Role:               "driver",
				MemoryBytes:        2 << 30,
				MemoryLimitBytes:   6 << 30,
				UtilizationPercent: 33.333,
				MetricsAvailable:   true,
			},
			{
				Name:               "executor-1",
				Role:               "executor",
				MemoryBytes:        13 << 30,
				MemoryLimitBytes:   40 << 30,
				UtilizationPercent: 32.5,
				MetricsAvailable:   true,
			},
		},
	}}
	api := newTestKPOMonitorAPI(transport, kube)
	_, output, err := api.watch(
		context.Background(),
		nil,
		watchKPOMemoryInput{
			Region:              "US-01",
			DAGID:               testKPODAG,
			RunID:               testKPORun,
			TaskID:              testKPOTask,
			BaselineTryNumber:   6,
			PollIntervalSeconds: 5,
			PollCount:           1,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if !output.RerunStarted || output.Complete ||
		output.CurrentTryNumber != 7 ||
		output.DriverPod != testKPODriver ||
		output.ApplicationSelector != "spark-123" ||
		len(output.History) != 1 ||
		output.Summary.PeakExecutorMemoryBytes != 13<<30 ||
		len(output.Graph.Points) != 4 {
		t.Fatalf("output = %#v", output)
	}
	if kube.calls != 1 || kube.context != "l3-us01" ||
		kube.namespace != "scheduler" ||
		kube.pod != testKPODriver {
		t.Fatalf("kube = %#v", kube)
	}
}

func TestWatchKPOMemoryWaitsForNewTryWithoutSamplingOldAttempt(t *testing.T) {
	t.Parallel()
	kube := &kpoSnapshotStub{}
	api := newTestKPOMonitorAPI(&kpoMonitorTransport{
		state:    "failed",
		try:      6,
		operator: "SparkSubmitOperator",
	}, kube)
	_, output, err := api.watch(
		context.Background(),
		nil,
		watchKPOMemoryInput{
			Region:              "US-01",
			DAGID:               testKPODAG,
			RunID:               testKPORun,
			TaskID:              testKPOTask,
			BaselineTryNumber:   6,
			PollIntervalSeconds: 5,
			PollCount:           1,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if output.RerunStarted || output.Complete || len(output.History) != 0 ||
		kube.calls != 0 ||
		!containsKPOString(output.Warnings, "waiting for an Airflow attempt newer than the baseline") {
		t.Fatalf("output = %#v, kube calls = %d", output, kube.calls)
	}
}

func TestKPOPollBoundsRejectsUnboundedWatch(t *testing.T) {
	t.Parallel()
	_, _, err := kpoPollBounds(60, 20)
	if err == nil || !strings.Contains(err.Error(), "must not exceed") {
		t.Fatalf("error = %v", err)
	}
}

func newTestKPOMonitorAPI(
	transport airflow.Transport,
	kube kpoSnapshotSource,
) *kpoMonitorAPI {
	source := airflow.NewSource([]airflow.RegionConfig{{
		Region:      prodsupport.US01,
		Credentials: airflow.Credentials{Host: "https://airflow"},
	}}, transport)
	return &kpoMonitorAPI{
		airflow: &airflowAPI{source: source},
		kube:    kube,
		sleep: func(context.Context, time.Duration) error {
			return nil
		},
	}
}

func containsKPOString(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}

func TestKPOMonitorToolsAreReadOnly(t *testing.T) {
	t.Parallel()
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	source := airflow.NewSource([]airflow.RegionConfig{{
		Region:      prodsupport.US01,
		Credentials: airflow.Credentials{},
	}}, &kpoMonitorTransport{})
	if err := registerKPOMonitor(server, &airflowAPI{source: source}); err != nil {
		t.Fatal(err)
	}
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	if _, err := server.Connect(context.Background(), serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "1"}, nil)
	session, err := client.Connect(context.Background(), clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()
	result, err := session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Tools) != 2 {
		t.Fatalf("tools = %#v", result.Tools)
	}
	for _, tool := range result.Tools {
		if tool.Annotations == nil || !tool.Annotations.ReadOnlyHint ||
			tool.Annotations.DestructiveHint == nil ||
			*tool.Annotations.DestructiveHint {
			t.Fatalf("%s annotations = %#v", tool.Name, tool.Annotations)
		}
	}
}
