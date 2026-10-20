package kubernetes

import (
	"context"
	"fmt"
	"strings"
)

// Preflight verifies that the configured context can read pod metrics.
func (s *Source) Preflight(
	ctx context.Context,
	clusterContext string,
	namespace string,
) error {
	for field, value := range map[string]string{
		"cluster context": clusterContext,
		"namespace":       namespace,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", field)
		}
	}
	allowed, err := s.command(
		ctx,
		"--context", clusterContext,
		"auth", "can-i", "get", "pods.metrics.k8s.io",
		"--namespace", namespace,
	)
	if err != nil {
		return err
	}
	if strings.TrimSpace(string(allowed)) != "yes" {
		return fmt.Errorf(
			"context %s cannot read pod metrics in namespace %s",
			clusterContext,
			namespace,
		)
	}
	_, err = s.command(
		ctx,
		"--context", clusterContext,
		"get", "--raw", "/apis/metrics.k8s.io/v1beta1",
	)
	if err != nil {
		return fmt.Errorf("Kubernetes Metrics API is unavailable: %w", err)
	}
	return nil
}
