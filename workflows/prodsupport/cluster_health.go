package prodsupport

import (
	"fmt"
	"strings"
	"time"
)

// ClusterHealthState identifies evidence-derived regional health.
type ClusterHealthState string

const (
	ClusterHealthy   ClusterHealthState = "healthy"
	ClusterUnhealthy ClusterHealthState = "unhealthy"
	ClusterUnknown   ClusterHealthState = "unknown"
)

// RegionalClusterHealth contains read-only regional health evidence.
type RegionalClusterHealth struct {
	Region                 Region
	ObservedAt             *time.Time
	ApplicationHealthy     *bool
	PodsHealthy            *bool
	DAGsParsingHealthy     *bool
	ActiveDAGCount         *int
	RestartCount           *int
	CumulativeRestartCount *int
	RestartWindowStart     *time.Time
	RestartWindowEnd       *time.Time
	KEDAStatus             string
	Symptoms               []string
	Warnings               []string
}

// Validate rejects contradictory or incomplete boundary values.
func (h RegionalClusterHealth) Validate() error {
	if h.ActiveDAGCount != nil && *h.ActiveDAGCount < 0 {
		return fmt.Errorf("active_dag_count must not be negative")
	}
	for _, value := range []*int{h.RestartCount, h.CumulativeRestartCount} {
		if value != nil && *value < 0 {
			return fmt.Errorf("restart_count must not be negative")
		}
	}
	if (h.RestartWindowStart != nil || h.RestartWindowEnd != nil) &&
		(h.RestartWindowStart == nil || h.RestartWindowEnd == nil ||
			!h.RestartWindowStart.Before(*h.RestartWindowEnd)) {
		return fmt.Errorf("restart window timestamps must be timezone-aware and ordered")
	}
	keda := h.KEDAStatus
	if keda == "" {
		keda = "unknown"
	}
	if strings.TrimSpace(keda) == "" {
		return fmt.Errorf("keda_status must not be empty")
	}
	for _, item := range append(append([]string(nil), h.Symptoms...), h.Warnings...) {
		if strings.TrimSpace(item) == "" {
			return fmt.Errorf("cluster-health symptoms and warnings must not be empty")
		}
	}
	return nil
}

// State derives health from primary checks without promoting warnings.
func (h RegionalClusterHealth) State() ClusterHealthState {
	for _, value := range []*bool{h.ApplicationHealthy, h.PodsHealthy, h.DAGsParsingHealthy} {
		if value != nil && !*value {
			return ClusterUnhealthy
		}
	}
	if h.ActiveDAGCount != nil && *h.ActiveDAGCount == 0 {
		return ClusterUnhealthy
	}
	known := 0
	for _, value := range []*bool{h.ApplicationHealthy, h.PodsHealthy, h.DAGsParsingHealthy} {
		if value != nil {
			known++
		}
	}
	if known > 0 && (h.ActiveDAGCount == nil || *h.ActiveDAGCount > 0) {
		return ClusterHealthy
	}
	return ClusterUnknown
}

// UnavailableClusterHealth returns an explicit evidence gap.
func UnavailableClusterHealth(region Region) RegionalClusterHealth {
	return RegionalClusterHealth{
		Region: region, KEDAStatus: "unknown",
		Symptoms: []string{"cluster health evidence is unavailable"},
	}
}
