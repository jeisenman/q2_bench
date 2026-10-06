package ports

import (
	"context"
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// CortexRequest is one model inference request.
type CortexRequest struct {
	Model       string
	Prompt      string
	Temperature float64
}

// Validate checks the request at the provider boundary.
func (r CortexRequest) Validate() error {
	if strings.TrimSpace(r.Model) == "" {
		return fmt.Errorf("model must not be empty")
	}
	if strings.TrimSpace(r.Prompt) == "" {
		return fmt.Errorf("prompt must not be empty")
	}
	if r.Temperature < 0 || r.Temperature > 1 {
		return fmt.Errorf(
			"temperature must be between 0.0 and 1.0; got %v",
			r.Temperature,
		)
	}
	return nil
}

// CortexResponse is one completion and its execution environment.
type CortexResponse struct {
	Text        string
	Model       string
	Environment domain.Environment
	Recorded    bool
}

// CortexInference runs model inference outside deterministic SQL.
type CortexInference interface {
	Environment() domain.Environment
	Complete(context.Context, CortexRequest) (CortexResponse, error)
	CountTokens(context.Context, string, string) (int, error)
}
