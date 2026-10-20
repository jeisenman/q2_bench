package kpomonitor

import (
	"regexp"
	"strings"
)

var driverPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)path to spark driver pod:\s*([a-z0-9.-]+):([a-z0-9][a-z0-9.-]*-driver)\b`),
	regexp.MustCompile(`(?i)driver\s+([a-z0-9.-]+):([a-z0-9][a-z0-9.-]*-driver)\s+(?:badly exited|killed)`),
	regexp.MustCompile(`(?i)identified spark driver pod:\s*([a-z0-9][a-z0-9.-]*-driver)\b`),
	regexp.MustCompile(`(?i)\bpod name:\s*([a-z0-9][a-z0-9.-]*-driver)\b`),
	regexp.MustCompile(`(?i)found matching pod\s+([a-z0-9][a-z0-9.-]+)\b`),
	regexp.MustCompile(`(?i)\bpod\s+([a-z0-9][a-z0-9.-]+)\s+returned a failure\b`),
}

// PodReference identifies the Kubernetes pod emitted by an Airflow task log.
type PodReference struct {
	Namespace string `json:"namespace"`
	Name      string `json:"name"`
}

// PodReferenceFromLog extracts the last supported Spark or KPO pod reference.
func PodReferenceFromLog(log string, defaultNamespace string) (PodReference, bool) {
	namespace := strings.TrimSpace(defaultNamespace)
	if namespace == "" {
		namespace = "scheduler"
	}
	var reference PodReference
	lastStart := -1
	found := false
	for _, pattern := range driverPatterns {
		matches := pattern.FindAllStringSubmatchIndex(log, -1)
		for _, match := range matches {
			if len(match) < 4 || match[0] < lastStart {
				continue
			}
			switch len(match) {
			case 3:
				continue
			case 4:
				reference = PodReference{
					Namespace: namespace,
					Name:      strings.ToLower(log[match[2]:match[3]]),
				}
			case 6:
				reference = PodReference{
					Namespace: strings.ToLower(log[match[2]:match[3]]),
					Name:      strings.ToLower(log[match[4]:match[5]]),
				}
			default:
				continue
			}
			lastStart = match[0]
			found = true
		}
	}
	return reference, found
}

// SupportedOperator reports whether the monitor can map the operator to pods.
func SupportedOperator(operator string) bool {
	switch strings.TrimSpace(operator) {
	case "SparkSubmitOperator", "KubernetesPodOperator":
		return true
	default:
		return false
	}
}
