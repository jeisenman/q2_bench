// Package agents contains provider-neutral data-engineering agents.
package agents

import (
	"context"

	"github.com/jeisenman/q2_bench/domain"
)

// Agent exposes immutable metadata and executes validated requests.
type Agent interface {
	Definition() domain.AgentDefinition
	Run(context.Context, domain.AgentRequest) (domain.AgentResult, error)
}
