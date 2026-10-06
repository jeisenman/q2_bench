// Package ports defines provider-neutral infrastructure boundaries.
package ports

import (
	"context"
	"path/filepath"

	"github.com/jeisenman/q2_bench/domain"
)

// ArtifactStore persists and retrieves run artifacts.
type ArtifactStore interface {
	Put(context.Context, string, string, string) (string, error)
	Get(context.Context, string, string) (string, error)
}

// DatasetProvider reads named records without exposing provider clients.
type DatasetProvider interface {
	FetchRecords(
		context.Context,
		string,
		domain.Attributes,
		int,
	) ([]domain.Attributes, error)
}

// Evaluation scores an agent result against benchmark-owned criteria.
type Evaluation interface {
	Evaluate(
		context.Context,
		domain.BenchmarkIdentity,
		domain.AgentRequest,
		domain.AgentResult,
	) (domain.Attributes, error)
}

// Runtime executes framework-neutral agent definitions.
type Runtime interface {
	Run(context.Context, domain.AgentDefinition, domain.AgentRequest) (domain.AgentResult, error)
}

// SecretProvider resolves secrets without exposing a concrete secret manager.
type SecretProvider interface {
	GetSecret(context.Context, string) (string, error)
}

// Tracking records agent and benchmark activity.
type Tracking interface {
	StartRun(context.Context, domain.BenchmarkIdentity, domain.AgentRequest) (string, error)
	LogResult(context.Context, string, domain.AgentResult) error
	AnnotateFailure(context.Context, string, string, string, domain.Attributes) error
}

// SQLProbe verifies read-only analytics connectivity.
type SQLProbe interface {
	Probe(context.Context) error
}

// CortexProbe verifies Cortex connectivity.
type CortexProbe interface {
	ProbeCortex(context.Context) error
}

// BlobProbe verifies that an ADLS blob can be addressed.
type BlobProbe interface {
	ProbeBlob(context.Context, string, string) error
}

// CleanPath returns a platform-native artifact path.
func CleanPath(path string) string {
	return filepath.Clean(path)
}
