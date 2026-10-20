package kpomonitor

import (
	"strings"
	"testing"
)

func TestPodReferenceFromSparkLog(t *testing.T) {
	t.Parallel()
	log := `
Identified spark driver pod: old-job-11111111-1111-1111-1111-111111111111-driver
ERROR : Driver scheduler:high-quality-core-account-financial-statements-2f69309e-723e-42cf-9375-4020e6f44208-driver badly exited
`
	reference, found := PodReferenceFromLog(log, "scheduler")
	if !found {
		t.Fatal("driver pod was not found")
	}
	if reference.Namespace != "scheduler" ||
		reference.Name != "high-quality-core-account-financial-statements-2f69309e-723e-42cf-9375-4020e6f44208-driver" {
		t.Fatalf("reference = %#v", reference)
	}
}

func TestPodReferenceFromKPOLogUsesDefaultNamespace(t *testing.T) {
	t.Parallel()
	reference, found := PodReferenceFromLog(
		"Found matching pod copy-client-data-abc123 with labels",
		"scheduler",
	)
	if !found || reference.Namespace != "scheduler" ||
		reference.Name != "copy-client-data-abc123" {
		t.Fatalf("reference = %#v, found = %v", reference, found)
	}
}

func TestProfileSummaryAndGraph(t *testing.T) {
	t.Parallel()
	first, err := NewMemorySample("running", 7, ApplicationSnapshot{
		ObservedAt: "2026-10-15T19:00:00Z",
		DriverPod:  "driver",
		Pods: []PodMemorySample{
			{Name: "driver", Role: "driver", MemoryBytes: 2 << 30},
			{
				Name: "executor-1", Role: "executor", MemoryBytes: 10 << 30,
				MemoryLimitBytes: 12 << 30, UtilizationPercent: 83.333,
			},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	second, err := NewMemorySample("failed", 7, ApplicationSnapshot{
		ObservedAt: "2026-10-15T19:01:00Z",
		DriverPod:  "driver",
		Pods: []PodMemorySample{{
			Name: "executor-2", Role: "executor", MemoryBytes: 12 << 30,
			MemoryLimitBytes: 12 << 30, UtilizationPercent: 100, OOMKilled: true,
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	summary := Summarize([]MemorySample{first, second})
	if !summary.OOMObserved || summary.PeakExecutorMemoryBytes != 12<<30 ||
		summary.PeakTotalMemoryBytes != 12<<30 {
		t.Fatalf("summary = %#v", summary)
	}
	graph := BuildGraph([]MemorySample{first, second})
	if len(graph.Points) != 8 ||
		!strings.Contains(graph.Preview, "max executor GiB") {
		t.Fatalf("graph = %#v", graph)
	}
}

func TestAppendHistoryRejectsOversizedPayload(t *testing.T) {
	t.Parallel()
	history := make([]MemorySample, MaxHistorySamples)
	_, err := AppendHistory(history, MemorySample{
		ObservedAt: "2026-10-15T19:00:00Z", DriverPod: "driver", TryNumber: 1,
	})
	if err == nil || !strings.Contains(err.Error(), "exceeds maximum") {
		t.Fatalf("error = %v", err)
	}
}
