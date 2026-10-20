// Package kubernetes reads bounded Kubernetes pod and metrics evidence.
package kubernetes

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os/exec"
	"sort"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/kpomonitor"
)

const sparkSelectorLabel = "spark-app-selector"

// CommandRunner executes one bounded kubectl command.
type CommandRunner func(context.Context, string, ...string) ([]byte, error)

// Source reads one pod or Spark application from a configured context.
type Source struct {
	Run CommandRunner
	Now func() time.Time
}

// PodNotFoundError reports an expected gap while a workload is starting.
type PodNotFoundError struct {
	Name string
}

func (e *PodNotFoundError) Error() string {
	return fmt.Sprintf("Kubernetes pod %s was not found", e.Name)
}

// NewSource constructs a kubectl-backed metrics source.
func NewSource(run CommandRunner) *Source {
	if run == nil {
		run = func(ctx context.Context, name string, args ...string) ([]byte, error) {
			return exec.CommandContext(ctx, name, args...).CombinedOutput()
		}
	}
	return &Source{Run: run, Now: time.Now}
}

// Snapshot reads current usage, limits, roles, and OOM termination evidence.
func (s *Source) Snapshot(
	ctx context.Context,
	clusterContext string,
	namespace string,
	podName string,
) (kpomonitor.ApplicationSnapshot, error) {
	for field, value := range map[string]string{
		"cluster context": clusterContext,
		"namespace":       namespace,
		"pod name":        podName,
	} {
		if strings.TrimSpace(value) == "" {
			return kpomonitor.ApplicationSnapshot{}, fmt.Errorf("%s must not be empty", field)
		}
	}
	driverContent, err := s.command(
		ctx,
		"--context", clusterContext,
		"--namespace", namespace,
		"get", "pod", podName,
		"--output", "json",
	)
	if err != nil {
		if commandContains(err, "not found") {
			return kpomonitor.ApplicationSnapshot{}, &PodNotFoundError{Name: podName}
		}
		return kpomonitor.ApplicationSnapshot{}, err
	}
	driver, err := decodePod(driverContent)
	if err != nil {
		return kpomonitor.ApplicationSnapshot{}, err
	}
	selector := strings.TrimSpace(driver.Metadata.Labels[sparkSelectorLabel])
	pods, metrics, err := s.applicationEvidence(
		ctx,
		clusterContext,
		namespace,
		driver,
		selector,
	)
	if err != nil {
		return kpomonitor.ApplicationSnapshot{}, err
	}
	now := s.Now
	if now == nil {
		now = time.Now
	}
	return makeSnapshot(now().UTC(), driver.Metadata.Name, selector, pods, metrics)
}

type commandError struct {
	Command string
	Output  string
	Err     error
}

func (e *commandError) Error() string {
	if e.Output == "" {
		return fmt.Sprintf("%s failed: %v", e.Command, e.Err)
	}
	return fmt.Sprintf("%s failed: %s", e.Command, e.Output)
}

func (e *commandError) Unwrap() error {
	return e.Err
}

func (s *Source) command(ctx context.Context, args ...string) ([]byte, error) {
	content, err := s.Run(ctx, "kubectl", args...)
	if err == nil {
		return content, nil
	}
	return nil, &commandError{
		Command: "kubectl " + strings.Join(args, " "),
		Output:  strings.TrimSpace(string(content)),
		Err:     err,
	}
}

func commandContains(err error, marker string) bool {
	var commandErr *commandError
	return errors.As(err, &commandErr) &&
		strings.Contains(strings.ToLower(commandErr.Output), strings.ToLower(marker))
}

func (s *Source) applicationEvidence(
	ctx context.Context,
	clusterContext string,
	namespace string,
	driver kubernetesPod,
	selector string,
) ([]kubernetesPod, []podMetrics, error) {
	if selector == "" {
		path := fmt.Sprintf(
			"/apis/metrics.k8s.io/v1beta1/namespaces/%s/pods/%s",
			url.PathEscape(namespace),
			url.PathEscape(driver.Metadata.Name),
		)
		content, err := s.command(ctx, "--context", clusterContext, "get", "--raw", path)
		if err != nil {
			return nil, nil, err
		}
		metric, err := decodePodMetric(content)
		if err != nil {
			return nil, nil, err
		}
		return []kubernetesPod{driver}, []podMetrics{metric}, nil
	}
	labelSelector := sparkSelectorLabel + "=" + selector
	podContent, err := s.command(
		ctx,
		"--context", clusterContext,
		"--namespace", namespace,
		"get", "pods",
		"--selector", labelSelector,
		"--output", "json",
	)
	if err != nil {
		return nil, nil, err
	}
	pods, err := decodePodList(podContent)
	if err != nil {
		return nil, nil, err
	}
	metricsPath := fmt.Sprintf(
		"/apis/metrics.k8s.io/v1beta1/namespaces/%s/pods?labelSelector=%s",
		url.PathEscape(namespace),
		url.QueryEscape(labelSelector),
	)
	metricsContent, err := s.command(
		ctx,
		"--context", clusterContext,
		"get", "--raw", metricsPath,
	)
	if err != nil {
		return nil, nil, err
	}
	metrics, err := decodePodMetricList(metricsContent)
	if err != nil {
		return nil, nil, err
	}
	return pods, metrics, nil
}

type kubernetesPod struct {
	Metadata struct {
		Name   string            `json:"name"`
		Labels map[string]string `json:"labels"`
	} `json:"metadata"`
	Spec struct {
		Containers []struct {
			Name      string `json:"name"`
			Resources struct {
				Limits map[string]string `json:"limits"`
			} `json:"resources"`
		} `json:"containers"`
	} `json:"spec"`
	Status struct {
		ContainerStatuses []struct {
			Name      string         `json:"name"`
			State     containerState `json:"state"`
			LastState containerState `json:"lastState"`
		} `json:"containerStatuses"`
	} `json:"status"`
}

type containerState struct {
	Terminated *struct {
		Reason string `json:"reason"`
	} `json:"terminated"`
}

type podMetrics struct {
	Metadata struct {
		Name string `json:"name"`
	} `json:"metadata"`
	Containers []struct {
		Name  string            `json:"name"`
		Usage map[string]string `json:"usage"`
	} `json:"containers"`
}

type podList struct {
	Items []kubernetesPod `json:"items"`
}

type podMetricList struct {
	Items []podMetrics `json:"items"`
}

func decodePod(content []byte) (kubernetesPod, error) {
	var pod kubernetesPod
	if err := json.Unmarshal(content, &pod); err != nil {
		return kubernetesPod{}, fmt.Errorf("decode Kubernetes pod: %w", err)
	}
	if strings.TrimSpace(pod.Metadata.Name) == "" {
		return kubernetesPod{}, fmt.Errorf("Kubernetes pod response is missing metadata.name")
	}
	return pod, nil
}

func decodePodList(content []byte) ([]kubernetesPod, error) {
	var payload podList
	if err := json.Unmarshal(content, &payload); err != nil {
		return nil, fmt.Errorf("decode Kubernetes pod list: %w", err)
	}
	return payload.Items, nil
}

func decodePodMetric(content []byte) (podMetrics, error) {
	var metric podMetrics
	if err := json.Unmarshal(content, &metric); err != nil {
		return podMetrics{}, fmt.Errorf("decode Kubernetes pod metrics: %w", err)
	}
	if strings.TrimSpace(metric.Metadata.Name) == "" {
		return podMetrics{}, fmt.Errorf("Kubernetes pod metrics are missing metadata.name")
	}
	return metric, nil
}

func decodePodMetricList(content []byte) ([]podMetrics, error) {
	var payload podMetricList
	if err := json.Unmarshal(content, &payload); err != nil {
		return nil, fmt.Errorf("decode Kubernetes pod metrics list: %w", err)
	}
	return payload.Items, nil
}

func makeSnapshot(
	observedAt time.Time,
	driverPod string,
	selector string,
	pods []kubernetesPod,
	metrics []podMetrics,
) (kpomonitor.ApplicationSnapshot, error) {
	metricsByPod := make(map[string]podMetrics, len(metrics))
	for _, metric := range metrics {
		metricsByPod[metric.Metadata.Name] = metric
	}
	samples := make([]kpomonitor.PodMemorySample, 0, len(pods))
	warnings := make([]string, 0)
	for _, pod := range pods {
		sample, err := makePodSample(pod, metricsByPod[pod.Metadata.Name])
		if err != nil {
			return kpomonitor.ApplicationSnapshot{}, err
		}
		if !sample.MetricsAvailable {
			warnings = append(warnings, "memory metrics unavailable for pod "+sample.Name)
		}
		samples = append(samples, sample)
	}
	sort.Slice(samples, func(left, right int) bool {
		if samples[left].Role != samples[right].Role {
			return samples[left].Role < samples[right].Role
		}
		return samples[left].Name < samples[right].Name
	})
	return kpomonitor.ApplicationSnapshot{
		ObservedAt:          observedAt.Format(time.RFC3339Nano),
		DriverPod:           driverPod,
		ApplicationSelector: selector,
		Pods:                samples,
		Warnings:            warnings,
	}, nil
}

func makePodSample(
	pod kubernetesPod,
	metrics podMetrics,
) (kpomonitor.PodMemorySample, error) {
	sample := kpomonitor.PodMemorySample{
		Name: pod.Metadata.Name,
		Role: strings.TrimSpace(pod.Metadata.Labels["spark-role"]),
	}
	if sample.Role == "" {
		sample.Role = "pod"
	}
	limits := make(map[string]uint64, len(pod.Spec.Containers))
	for _, container := range pod.Spec.Containers {
		rawLimit := strings.TrimSpace(container.Resources.Limits["memory"])
		if rawLimit == "" {
			continue
		}
		limit, err := ParseMemoryQuantity(rawLimit)
		if err != nil {
			return kpomonitor.PodMemorySample{}, fmt.Errorf(
				"pod %s container %s memory limit: %w",
				pod.Metadata.Name,
				container.Name,
				err,
			)
		}
		limits[container.Name] = limit
		sample.MemoryLimitBytes += limit
	}
	for _, container := range metrics.Containers {
		rawMemory := strings.TrimSpace(container.Usage["memory"])
		if rawMemory == "" {
			continue
		}
		memory, err := ParseMemoryQuantity(rawMemory)
		if err != nil {
			return kpomonitor.PodMemorySample{}, fmt.Errorf(
				"pod %s container %s memory usage: %w",
				pod.Metadata.Name,
				container.Name,
				err,
			)
		}
		sample.MemoryBytes += memory
		sample.MetricsAvailable = true
	}
	if sample.MemoryLimitBytes > 0 {
		sample.UtilizationPercent =
			float64(sample.MemoryBytes) / float64(sample.MemoryLimitBytes) * 100
	}
	for _, status := range pod.Status.ContainerStatuses {
		if terminationReason(status.State) == "oomkilled" ||
			terminationReason(status.LastState) == "oomkilled" {
			sample.OOMKilled = true
		}
	}
	return sample, nil
}

func terminationReason(state containerState) string {
	if state.Terminated == nil {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(state.Terminated.Reason))
}
