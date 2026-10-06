package prodsupport

import (
	"strings"
	"testing"
	"time"
)

func testFailure() AirflowFailure {
	return AirflowFailure{
		Region: US01, DAGID: "dag", RunID: "run", TaskID: "task",
		StartAt:   time.Date(2026, 9, 25, 5, 0, 0, 0, time.UTC),
		EndAt:     time.Date(2026, 9, 25, 6, 0, 0, 0, time.UTC),
		TryNumber: 1,
	}
}

func TestResolveQueryWindow(t *testing.T) {
	t.Parallel()
	reference := time.Date(2026, 9, 25, 12, 0, 0, 0, time.UTC)
	tests := map[string]string{
		"do prod support":                         "2026-09-24T05:00:00Z",
		"Do yesterday's prod support":             "2026-09-23T05:00:00Z",
		"Do prod support for 9/21/26.":            "2026-09-21T05:00:00Z",
		"run/date_start 2026-03-14, 05:00:00 UTC": "2026-03-14T05:00:00Z",
	}
	for prompt, expected := range tests {
		window, err := ResolveQueryWindow(prompt, reference)
		if err != nil {
			t.Fatal(err)
		}
		if got := window.FailedSince.Format(time.RFC3339); got != expected {
			t.Fatalf("%q resolved to %s", prompt, got)
		}
	}
}

func TestClassifyLog(t *testing.T) {
	t.Parallel()
	tests := map[string]FailureKind{
		"Distinctness validation failed for Accounts": Distinctness,
		"container status OOMKilled":                  ConfirmedOOM,
		"**TimeoutError: task expired":                OMSConfirmedTimeout,
		"SIGKILL under memory pressure":               ProbableOOM,
		"process exit -9":                             UnknownResourceTermination,
		"Traceback: ValueError":                       ApplicationError,
		"worker stopped":                              Unknown,
	}
	for log, expected := range tests {
		if got := ClassifyLog(testFailure(), log, UnknownEvidence).Kind; got != expected {
			t.Fatalf("ClassifyLog(%q) = %q", log, got)
		}
	}
}

func TestSummarizeTaskLog(t *testing.T) {
	t.Parallel()
	summary, err := SummarizeTaskLog("noise\nOOMKilled\nmore noise", 3, 1200)
	if err != nil {
		t.Fatal(err)
	}
	if summary.Status != EvidenceTerminal || summary.Excerpt != "OOMKilled" {
		t.Fatalf("summary = %#v", summary)
	}
}

func TestWorkloadRouting(t *testing.T) {
	t.Parallel()
	metadata := AirflowTaskMetadata{
		DAGID: "dag", TaskID: "task",
		OperatorName: "airflow.providers.spark.SparkSubmitOperator",
	}
	if ClassifyWorkload(metadata) != SparkBatch {
		t.Fatal("expected Spark workload")
	}
	route := RouteOMSEvidence(SparkBatch, CA02)
	if route == nil || route.WorkspaceName != "pl-oms-ca-primary" {
		t.Fatalf("route = %#v", route)
	}
}

func TestRetrySelectionAndGrouping(t *testing.T) {
	t.Parallel()
	candidates := []RetryCandidate{
		{Number: 1, Region: US01, DAGID: "dag-1", RunID: "run", TaskID: "task-1"},
		{Number: 2, Region: CA02, DAGID: "dag-2", RunID: "run", TaskID: "task-2"},
		{Number: 3, Region: CA02, DAGID: "dag-2", RunID: "run", TaskID: "task-3"},
	}
	selected, err := SelectRetryCandidates("retry CA", candidates)
	if err != nil {
		t.Fatal(err)
	}
	if len(selected) != 2 || selected[0].Number != 2 {
		t.Fatalf("selected = %#v", selected)
	}
	batches := RetryBatches(selected)
	if len(batches) != 1 || len(batches[0].TaskIDs) != 2 {
		t.Fatalf("batches = %#v", batches)
	}
	_, err = SelectRetryCandidates("inspect job 1", candidates)
	if err == nil || !strings.Contains(err.Error(), "must request") {
		t.Fatalf("error = %v", err)
	}
}
