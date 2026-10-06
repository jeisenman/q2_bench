package agentmemory

import (
	"context"
	"crypto/rand"
	"fmt"
	"strings"
)

const DefaultAliasConfirmations = 3

// Memory manages one agent's durable memories within an explicit scope.
type Memory struct {
	store              Store
	AgentID            string
	Scope              Scope
	AliasConfirmations int
}

// New validates and constructs scoped memory policy.
func New(store Store, agentID string, scope Scope, aliasConfirmations int) (*Memory, error) {
	if store == nil {
		return nil, fmt.Errorf("memory store must not be nil")
	}
	if strings.TrimSpace(agentID) == "" {
		return nil, fmt.Errorf("agent_id must not be empty")
	}
	if err := scope.Validate(); err != nil {
		return nil, err
	}
	if aliasConfirmations == 0 {
		aliasConfirmations = DefaultAliasConfirmations
	}
	if aliasConfirmations < 1 {
		return nil, fmt.Errorf("alias_confirmations must be at least 1")
	}
	return &Memory{
		store: store, AgentID: agentID, Scope: scope,
		AliasConfirmations: aliasConfirmations,
	}, nil
}

// ResolveAlias resolves an alias without semantic similarity.
func (m *Memory) ResolveAlias(ctx context.Context, alias string) (AliasResolution, error) {
	key, err := NormalizeKey(alias)
	if err != nil {
		return AliasResolution{}, err
	}
	matches, err := m.store.Find(ctx, m.AgentID, m.Scope, AliasKind, key)
	if err != nil {
		return AliasResolution{}, err
	}
	active := make([]Record, 0, len(matches))
	for _, memory := range matches {
		if memory.Status == Proposed || memory.Status == Confirmed {
			active = append(active, memory)
		}
	}
	status := AliasNotFound
	switch {
	case len(active) > 1:
		status = AliasAmbiguous
	case len(active) == 1 && active[0].Status == Confirmed:
		status = AliasResolved
	case len(active) == 1:
		status = AliasConfirmationRequired
	}
	return AliasResolution{Status: status, Matches: active}, nil
}

// ProposeAlias stores a proposed alias without treating it as authoritative.
func (m *Memory) ProposeAlias(
	ctx context.Context,
	alias, entityType, entityID, canonicalName string,
) (Record, error) {
	record := Record{
		ID: newID(), AgentID: m.AgentID, Scope: m.Scope, Kind: AliasKind,
		Key: alias, Content: fmt.Sprintf("%s refers to %s", alias, canonicalName),
		Status: Proposed,
		Metadata: []Metadata{
			{Name: "canonical_entity_id", Value: entityID},
			{Name: "canonical_entity_type", Value: entityType},
			{Name: "canonical_name", Value: canonicalName},
		},
	}
	return m.store.Put(ctx, record)
}

// RecordAliasEvidence records explicit alias confirmation or rejection.
func (m *Memory) RecordAliasEvidence(
	ctx context.Context,
	memoryID string,
	outcome EvidenceOutcome,
	correlationID string,
) (Record, error) {
	return m.store.RecordEvidence(
		ctx,
		m.AgentID,
		m.Scope,
		Evidence{MemoryID: memoryID, Outcome: outcome, CorrelationID: correlationID},
		m.AliasConfirmations,
	)
}

// RememberSummary stores one evidence-derived summary as confirmed memory.
func (m *Memory) RememberSummary(
	ctx context.Context,
	key, content string,
	metadata []Metadata,
	confidence float64,
) (Record, error) {
	if confidence == 0 {
		confidence = 1
	}
	return m.store.Put(ctx, Record{
		ID: newID(), AgentID: m.AgentID, Scope: m.Scope, Kind: SummaryKind,
		Key: key, Content: content, Status: Confirmed, Confidence: confidence,
		EvidenceCount: 1, Metadata: append([]Metadata(nil), metadata...),
	})
}

func newID() string {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		panic(fmt.Sprintf("generate memory ID: %v", err))
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4],
		value[4:6],
		value[6:8],
		value[8:10],
		value[10:16],
	)
}
