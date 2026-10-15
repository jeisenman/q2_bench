package mcpapi

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const minimumHealthyDAGCount = 10

var clusterContexts = map[prodsupport.Region]string{
	prodsupport.US01: "l3-us01",
	prodsupport.CA02: "l3-ca02",
}

type clusterHealthAPI struct {
	airflow *airflowAPI
	run     func(context.Context, string, ...string) ([]byte, error)
}

type inspectClusterHealthInput struct {
	Region  string `json:"region"`
	StartAt string `json:"start_at"`
	EndAt   string `json:"end_at"`
}

type kubernetesPodList struct {
	Items []kubernetesPod `json:"items"`
}

type kubernetesPod struct {
	Metadata struct {
		Name string `json:"name"`
	} `json:"metadata"`
	Status struct {
		Phase             string                      `json:"phase"`
		ContainerStatuses []kubernetesContainerStatus `json:"containerStatuses"`
	} `json:"status"`
}

type kubernetesContainerStatus struct {
	Ready        bool `json:"ready"`
	RestartCount int  `json:"restartCount"`
	LastState    struct {
		Terminated struct {
			FinishedAt string `json:"finishedAt"`
		} `json:"terminated"`
	} `json:"lastState"`
}

func newClusterHealthAPI(airflow *airflowAPI) *clusterHealthAPI {
	return &clusterHealthAPI{
		airflow: airflow,
		run: func(ctx context.Context, name string, args ...string) ([]byte, error) {
			return exec.CommandContext(ctx, name, args...).Output()
		},
	}
}

func addClusterHealthTool(server *mcp.Server, api *clusterHealthAPI) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "inspect_cluster_health",
		Description: "Check one production cluster and its current active DAG count.",
	}, api.inspect)
}

func (a *clusterHealthAPI) inspect(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input inspectClusterHealthInput,
) (*mcp.CallToolResult, map[string]any, error) {
	region := prodsupport.Region(input.Region)
	clusterContext, exists := clusterContexts[region]
	if !exists {
		return nil, nil, fmt.Errorf("region must be US-01 or CA-02")
	}
	startAt, endAt, err := clusterWindow(input.StartAt, input.EndAt)
	if err != nil {
		return nil, nil, err
	}
	content, err := a.run(
		ctx,
		"kubectl",
		"--context", clusterContext,
		"--namespace", "scheduler",
		"get", "pods",
		"--output", "json",
	)
	if err != nil {
		return nil, nil, fmt.Errorf(
			"production cluster %s is unavailable: %w",
			clusterContext,
			err,
		)
	}
	health, err := parsePodHealth(content, startAt, endAt)
	if err != nil {
		return nil, nil, err
	}
	activeDAGCount, err := a.airflow.source.ActiveDAGCount(ctx, region)
	if err != nil {
		return nil, nil, fmt.Errorf(
			"production cluster %s exists but active DAG count is unavailable: %w",
			clusterContext,
			err,
		)
	}
	dagsParsingHealthy := activeDAGCount >= minimumHealthyDAGCount
	return nil, map[string]any{
		"region": region, "cluster_context": clusterContext,
		"cluster_exists": true, "observed_at": time.Now().UTC().Format(time.RFC3339),
		"pods_healthy": health.podsHealthy, "unready_pods": health.unreadyPods,
		"restart_count":            health.restartCount,
		"cumulative_restart_count": health.cumulativeRestartCount,
		"restart_window_start":     startAt.Format(time.RFC3339),
		"restart_window_end":       endAt.Format(time.RFC3339),
		"active_dag_count":         activeDAGCount,
		"dags_parsing_healthy":     dagsParsingHealthy,
		"healthy":                  health.podsHealthy && dagsParsingHealthy,
	}, nil
}

type podHealth struct {
	podsHealthy            bool
	unreadyPods            []string
	restartCount           int
	cumulativeRestartCount int
}

func parsePodHealth(content []byte, startAt, endAt time.Time) (podHealth, error) {
	var payload kubernetesPodList
	if err := json.Unmarshal(content, &payload); err != nil {
		return podHealth{}, fmt.Errorf("decode kubectl pod response: %w", err)
	}
	result := podHealth{podsHealthy: true, unreadyPods: []string{}}
	for _, pod := range payload.Items {
		if pod.Status.Phase == "Succeeded" || pod.Status.Phase == "Failed" {
			continue
		}
		ready := pod.Status.Phase == "Running" && len(pod.Status.ContainerStatuses) > 0
		for _, status := range pod.Status.ContainerStatuses {
			result.cumulativeRestartCount += status.RestartCount
			ready = ready && status.Ready
			finishedAt := strings.TrimSpace(status.LastState.Terminated.FinishedAt)
			if finishedAt == "" {
				continue
			}
			finished, err := time.Parse(time.RFC3339Nano, finishedAt)
			if err != nil {
				return podHealth{}, fmt.Errorf(
					"pod %s has invalid restart timestamp: %w",
					pod.Metadata.Name,
					err,
				)
			}
			if !finished.Before(startAt) && finished.Before(endAt) {
				result.restartCount++
			}
		}
		if !ready {
			result.podsHealthy = false
			name := strings.TrimSpace(pod.Metadata.Name)
			if name == "" {
				name = "unknown pod"
			}
			result.unreadyPods = append(result.unreadyPods, name)
		}
	}
	return result, nil
}

func clusterWindow(start, end string) (time.Time, time.Time, error) {
	startAt, err := time.Parse(time.RFC3339, start)
	if err != nil {
		return time.Time{}, time.Time{}, fmt.Errorf(
			"start_at must be RFC3339 with a timezone: %w",
			err,
		)
	}
	endAt, err := time.Parse(time.RFC3339, end)
	if err != nil {
		return time.Time{}, time.Time{}, fmt.Errorf(
			"end_at must be RFC3339 with a timezone: %w",
			err,
		)
	}
	if !endAt.After(startAt) {
		return time.Time{}, time.Time{}, fmt.Errorf("end_at must be later than start_at")
	}
	return startAt, endAt, nil
}
