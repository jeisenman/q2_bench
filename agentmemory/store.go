package agentmemory

import (
	"context"
	"fmt"
	"sync"
)

// Store persists and retrieves bounded memories.
type Store interface {
	Find(context.Context, string, Scope, Kind, string) ([]Record, error)
	Put(context.Context, Record) (Record, error)
	RecordEvidence(context.Context, string, Scope, Evidence, int) (Record, error)
}

// ConflictError indicates a scoped key or evidence event conflicts.
type ConflictError struct{ Message string }

func (e *ConflictError) Error() string { return e.Message }

// NotFoundError indicates evidence targeted an unavailable memory.
type NotFoundError struct{ MemoryID string }

func (e *NotFoundError) Error() string {
	return fmt.Sprintf("memory %s was not found in the requested scope", e.MemoryID)
}

type evidenceKey struct {
	MemoryID      string
	CorrelationID string
}

// MemoryStore is a concurrency-safe in-memory Store.
type MemoryStore struct {
	mu       sync.RWMutex
	records  map[string]Record
	evidence map[evidenceKey]EvidenceOutcome
}

// NewMemoryStore creates an empty in-memory store.
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		records: make(map[string]Record), evidence: make(map[evidenceKey]EvidenceOutcome),
	}
}

// Find returns active exact-key memories in deterministic order.
func (s *MemoryStore) Find(
	_ context.Context,
	agentID string,
	scope Scope,
	kind Kind,
	normalizedKey string,
) ([]Record, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	matches := make([]Record, 0)
	for _, memory := range s.records {
		key, err := memory.NormalizedKey()
		if err != nil {
			return nil, err
		}
		if memory.AgentID == agentID && memory.Scope == scope && memory.Kind == kind &&
			key == normalizedKey && memory.Status != Rejected && memory.Status != Superseded {
			matches = append(matches, cloneRecord(memory))
		}
	}
	sortRecords(matches)
	return matches, nil
}

// Put inserts one memory while rejecting conflicting scoped keys.
func (s *MemoryStore) Put(_ context.Context, memory Record) (Record, error) {
	if err := memory.Validate(); err != nil {
		return Record{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, existing := range s.records {
		if existing.Status == Rejected || existing.Status == Superseded ||
			!sameKey(existing, memory) {
			continue
		}
		if !equalMetadata(existing.Metadata, memory.Metadata) {
			return Record{}, &ConflictError{Message: fmt.Sprintf(
				"memory key %q already has a different meaning",
				memory.Key,
			)}
		}
		return cloneRecord(existing), nil
	}
	s.records[memory.ID] = cloneRecord(memory)
	return cloneRecord(memory), nil
}

// RecordEvidence atomically applies one idempotent feedback event.
func (s *MemoryStore) RecordEvidence(
	_ context.Context,
	agentID string,
	scope Scope,
	evidence Evidence,
	promoteAfter int,
) (Record, error) {
	if err := evidence.Validate(); err != nil {
		return Record{}, err
	}
	if promoteAfter < 1 {
		return Record{}, fmt.Errorf("promote_after must be at least 1")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	memory, exists := s.records[evidence.MemoryID]
	if !exists || memory.AgentID != agentID || memory.Scope != scope {
		return Record{}, &NotFoundError{MemoryID: evidence.MemoryID}
	}
	key := evidenceKey{MemoryID: evidence.MemoryID, CorrelationID: evidence.CorrelationID}
	if prior, exists := s.evidence[key]; exists {
		if prior != evidence.Outcome {
			return Record{}, &ConflictError{Message: fmt.Sprintf(
				"correlation %q already recorded different evidence",
				evidence.CorrelationID,
			)}
		}
		return cloneRecord(memory), nil
	}
	if evidence.Outcome == EvidenceRejected {
		memory.Status = Rejected
	} else {
		memory.EvidenceCount++
		memory.Confidence = min(1, float64(memory.EvidenceCount)/float64(promoteAfter))
		memory.Status = Proposed
		if memory.EvidenceCount >= promoteAfter {
			memory.Status = Confirmed
		}
	}
	s.records[evidence.MemoryID] = memory
	s.evidence[key] = evidence.Outcome
	return cloneRecord(memory), nil
}

func sameKey(left, right Record) bool {
	leftKey, leftErr := left.NormalizedKey()
	rightKey, rightErr := right.NormalizedKey()
	return leftErr == nil && rightErr == nil && left.AgentID == right.AgentID &&
		left.Scope == right.Scope && left.Kind == right.Kind && leftKey == rightKey
}

func equalMetadata(left, right []Metadata) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func cloneRecord(record Record) Record {
	record.Metadata = append([]Metadata(nil), record.Metadata...)
	record.Embedding = append([]float64(nil), record.Embedding...)
	return record
}
