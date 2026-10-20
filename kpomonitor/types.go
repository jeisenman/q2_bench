// Package kpomonitor defines deterministic memory-profile values for KPO and
// Spark workloads.
package kpomonitor

import (
	"fmt"
	"sort"
	"strings"
)

const (
	// MaxHistorySamples bounds profile payloads passed through MCP.
	MaxHistorySamples = 600
	// MaxPodsPerSample bounds one Spark application's sampled fan-out.
	MaxPodsPerSample = 128
)

// PodMemorySample records one pod's current memory usage and limit.
type PodMemorySample struct {
	Name               string  `json:"name"`
	Role               string  `json:"role"`
	MemoryBytes        uint64  `json:"memory_bytes"`
	MemoryLimitBytes   uint64  `json:"memory_limit_bytes,omitempty"`
	UtilizationPercent float64 `json:"utilization_percent,omitempty"`
	MetricsAvailable   bool    `json:"metrics_available"`
	OOMKilled          bool    `json:"oom_killed"`
}

// MemorySample records one bounded observation of an Airflow workload.
type MemorySample struct {
	ObservedAt             string            `json:"observed_at"`
	TaskState              string            `json:"task_state"`
	TryNumber              int               `json:"try_number"`
	DriverPod              string            `json:"driver_pod"`
	ApplicationSelector    string            `json:"application_selector,omitempty"`
	Pods                   []PodMemorySample `json:"pods"`
	TotalMemoryBytes       uint64            `json:"total_memory_bytes"`
	DriverMemoryBytes      uint64            `json:"driver_memory_bytes"`
	MaxExecutorMemoryBytes uint64            `json:"max_executor_memory_bytes"`
	MaxUtilizationPercent  float64           `json:"max_utilization_percent,omitempty"`
	OOMKilledPods          []string          `json:"oom_killed_pods"`
}

// ApplicationSnapshot is one Kubernetes application observation.
type ApplicationSnapshot struct {
	ObservedAt          string
	DriverPod           string
	ApplicationSelector string
	Pods                []PodMemorySample
	Warnings            []string
}

// ProfileSummary aggregates the observed memory history without inferring that
// an unobserved OOM did not occur.
type ProfileSummary struct {
	SampleCount             int      `json:"sample_count"`
	StartedAt               string   `json:"started_at,omitempty"`
	LastObservedAt          string   `json:"last_observed_at,omitempty"`
	PeakTotalMemoryBytes    uint64   `json:"peak_total_memory_bytes"`
	PeakDriverMemoryBytes   uint64   `json:"peak_driver_memory_bytes"`
	PeakExecutorMemoryBytes uint64   `json:"peak_executor_memory_bytes"`
	PeakUtilizationPercent  float64  `json:"peak_utilization_percent,omitempty"`
	OOMObserved             bool     `json:"oom_observed"`
	OOMKilledPods           []string `json:"oom_killed_pods"`
}

// NewMemorySample combines task identity with one Kubernetes snapshot.
func NewMemorySample(
	taskState string,
	tryNumber int,
	snapshot ApplicationSnapshot,
) (MemorySample, error) {
	if strings.TrimSpace(snapshot.ObservedAt) == "" {
		return MemorySample{}, fmt.Errorf("memory snapshot observed_at must not be empty")
	}
	if strings.TrimSpace(snapshot.DriverPod) == "" {
		return MemorySample{}, fmt.Errorf("memory snapshot driver pod must not be empty")
	}
	if strings.TrimSpace(taskState) == "" {
		return MemorySample{}, fmt.Errorf("Airflow task state must not be empty")
	}
	if tryNumber < 1 {
		return MemorySample{}, fmt.Errorf("Airflow try number must be positive")
	}
	if len(snapshot.Pods) > MaxPodsPerSample {
		return MemorySample{}, fmt.Errorf(
			"memory snapshot exceeds maximum of %d pods",
			MaxPodsPerSample,
		)
	}
	sample := MemorySample{
		ObservedAt:          snapshot.ObservedAt,
		TaskState:           taskState,
		TryNumber:           tryNumber,
		DriverPod:           snapshot.DriverPod,
		ApplicationSelector: snapshot.ApplicationSelector,
		Pods:                append([]PodMemorySample(nil), snapshot.Pods...),
		OOMKilledPods:       []string{},
	}
	for _, pod := range sample.Pods {
		sample.TotalMemoryBytes += pod.MemoryBytes
		if pod.Role == "driver" {
			sample.DriverMemoryBytes += pod.MemoryBytes
		}
		if pod.Role == "executor" && pod.MemoryBytes > sample.MaxExecutorMemoryBytes {
			sample.MaxExecutorMemoryBytes = pod.MemoryBytes
		}
		if pod.UtilizationPercent > sample.MaxUtilizationPercent {
			sample.MaxUtilizationPercent = pod.UtilizationPercent
		}
		if pod.OOMKilled {
			sample.OOMKilledPods = append(sample.OOMKilledPods, pod.Name)
		}
	}
	sort.Strings(sample.OOMKilledPods)
	return sample, nil
}

// AppendHistory validates and appends newly observed samples.
func AppendHistory(
	history []MemorySample,
	samples ...MemorySample,
) ([]MemorySample, error) {
	if len(history)+len(samples) > MaxHistorySamples {
		return nil, fmt.Errorf(
			"memory profile history exceeds maximum of %d samples",
			MaxHistorySamples,
		)
	}
	result := make([]MemorySample, 0, len(history)+len(samples))
	for _, sample := range append(append([]MemorySample(nil), history...), samples...) {
		if strings.TrimSpace(sample.ObservedAt) == "" ||
			strings.TrimSpace(sample.DriverPod) == "" ||
			sample.TryNumber < 1 ||
			len(sample.Pods) > MaxPodsPerSample {
			return nil, fmt.Errorf("memory profile history contains an invalid sample")
		}
		result = append(result, sample)
	}
	return result, nil
}

// Summarize returns peak observations and explicit OOM evidence.
func Summarize(samples []MemorySample) ProfileSummary {
	summary := ProfileSummary{
		SampleCount:   len(samples),
		OOMKilledPods: []string{},
	}
	oomPods := make(map[string]struct{})
	for index, sample := range samples {
		if index == 0 {
			summary.StartedAt = sample.ObservedAt
		}
		summary.LastObservedAt = sample.ObservedAt
		if sample.TotalMemoryBytes > summary.PeakTotalMemoryBytes {
			summary.PeakTotalMemoryBytes = sample.TotalMemoryBytes
		}
		if sample.DriverMemoryBytes > summary.PeakDriverMemoryBytes {
			summary.PeakDriverMemoryBytes = sample.DriverMemoryBytes
		}
		if sample.MaxExecutorMemoryBytes > summary.PeakExecutorMemoryBytes {
			summary.PeakExecutorMemoryBytes = sample.MaxExecutorMemoryBytes
		}
		if sample.MaxUtilizationPercent > summary.PeakUtilizationPercent {
			summary.PeakUtilizationPercent = sample.MaxUtilizationPercent
		}
		for _, pod := range sample.OOMKilledPods {
			oomPods[pod] = struct{}{}
		}
	}
	for pod := range oomPods {
		summary.OOMKilledPods = append(summary.OOMKilledPods, pod)
	}
	sort.Strings(summary.OOMKilledPods)
	summary.OOMObserved = len(summary.OOMKilledPods) > 0
	return summary
}
