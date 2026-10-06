// Package agentmemory implements deterministic scoped agent memory.
package agentmemory

import (
	"fmt"
	"math"
	"regexp"
	"sort"
	"strings"
)

var memoryKeyCharacters = regexp.MustCompile(`[^a-z0-9]+`)

// ScopeType identifies a memory visibility boundary.
type ScopeType string

const (
	UserScope         ScopeType = "user"
	TeamScope         ScopeType = "team"
	OrganizationScope ScopeType = "organization"
)

// Kind identifies a durable memory category.
type Kind string

const (
	AliasKind      Kind = "alias"
	FactKind       Kind = "fact"
	PreferenceKind Kind = "preference"
	SummaryKind    Kind = "summary"
)

// Status identifies a memory lifecycle state.
type Status string

const (
	Proposed   Status = "proposed"
	Confirmed  Status = "confirmed"
	Rejected   Status = "rejected"
	Superseded Status = "superseded"
)

// EvidenceOutcome identifies explicit feedback.
type EvidenceOutcome string

const (
	EvidenceConfirmed EvidenceOutcome = "confirmed"
	EvidenceRejected  EvidenceOutcome = "rejected"
)

// AliasResolutionStatus identifies an exact alias lookup outcome.
type AliasResolutionStatus string

const (
	AliasNotFound             AliasResolutionStatus = "not_found"
	AliasConfirmationRequired AliasResolutionStatus = "confirmation_required"
	AliasResolved             AliasResolutionStatus = "resolved"
	AliasAmbiguous            AliasResolutionStatus = "ambiguous"
)

// Scope identifies the tenant and audience that may retrieve a memory.
type Scope struct {
	TenantID string
	Type     ScopeType
	ID       string
}

// Validate checks all isolation fields.
func (s Scope) Validate() error {
	if strings.TrimSpace(s.TenantID) == "" {
		return fmt.Errorf("tenant_id must not be empty")
	}
	if strings.TrimSpace(s.ID) == "" {
		return fmt.Errorf("scope_id must not be empty")
	}
	switch s.Type {
	case UserScope, TeamScope, OrganizationScope:
		return nil
	default:
		return fmt.Errorf("scope_type must be a valid ScopeType")
	}
}

// Metadata is one deterministic memory metadata value.
type Metadata struct {
	Name  string
	Value string
}

// Record represents one bounded durable memory and optional embedding.
type Record struct {
	ID             string
	AgentID        string
	Scope          Scope
	Kind           Kind
	Key            string
	Content        string
	Status         Status
	Confidence     float64
	EvidenceCount  int
	Metadata       []Metadata
	Embedding      []float64
	EmbeddingModel string
}

// Validate checks bounded content, metadata, and vector values.
func (r Record) Validate() error {
	for name, value := range map[string]string{
		"memory_id": r.ID, "agent_id": r.AgentID, "key": r.Key, "content": r.Content,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", name)
		}
	}
	if err := r.Scope.Validate(); err != nil {
		return err
	}
	switch r.Kind {
	case AliasKind, FactKind, PreferenceKind, SummaryKind:
	default:
		return fmt.Errorf("kind must be a valid Kind")
	}
	switch r.Status {
	case Proposed, Confirmed, Rejected, Superseded:
	default:
		return fmt.Errorf("status must be a valid Status")
	}
	if r.Confidence < 0 || r.Confidence > 1 {
		return fmt.Errorf("confidence must be between 0 and 1")
	}
	if r.EvidenceCount < 0 {
		return fmt.Errorf("evidence_count must not be negative")
	}
	names := make(map[string]struct{}, len(r.Metadata))
	for _, item := range r.Metadata {
		if _, exists := names[item.Name]; exists {
			return fmt.Errorf("memory metadata keys must be unique")
		}
		names[item.Name] = struct{}{}
	}
	for _, value := range r.Embedding {
		if math.IsInf(value, 0) || math.IsNaN(value) {
			return fmt.Errorf("memory embedding values must be finite")
		}
	}
	if len(r.Embedding) > 0 && strings.TrimSpace(r.EmbeddingModel) == "" {
		return fmt.Errorf("embedding_model is required when embedding is present")
	}
	return nil
}

// NormalizedKey returns the punctuation-insensitive lookup key.
func (r Record) NormalizedKey() (string, error) {
	return NormalizeKey(r.Key)
}

// Evidence records one explicit feedback event.
type Evidence struct {
	MemoryID      string
	Outcome       EvidenceOutcome
	CorrelationID string
}

// Validate checks feedback identity and provenance.
func (e Evidence) Validate() error {
	if strings.TrimSpace(e.MemoryID) == "" {
		return fmt.Errorf("memory_id must not be empty")
	}
	switch e.Outcome {
	case EvidenceConfirmed, EvidenceRejected:
	default:
		return fmt.Errorf("outcome must be a valid EvidenceOutcome")
	}
	if strings.TrimSpace(e.CorrelationID) == "" {
		return fmt.Errorf("correlation_id must not be empty")
	}
	return nil
}

// AliasResolution contains exact alias matches and their resolution state.
type AliasResolution struct {
	Status  AliasResolutionStatus
	Matches []Record
}

// Unique returns the sole memory when cardinality is one.
func (r AliasResolution) Unique() (Record, bool) {
	if len(r.Matches) != 1 {
		return Record{}, false
	}
	return r.Matches[0], true
}

// NormalizeKey returns a stable punctuation-insensitive lookup key.
func NormalizeKey(value string) (string, error) {
	if strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("memory key must not be empty")
	}
	return strings.TrimSpace(memoryKeyCharacters.ReplaceAllString(strings.ToLower(value), " ")), nil
}

func sortRecords(records []Record) {
	sort.Slice(records, func(left, right int) bool { return records[left].ID < records[right].ID })
}
