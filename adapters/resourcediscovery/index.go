// Package resourcediscovery implements local and HTTP resource discovery adapters.
package resourcediscovery

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	agent "github.com/jeisenman/q2_bench/agents/resourcediscovery"
)

// JSONClientLookupSource reads an immutable non-secret client lookup.
type JSONClientLookupSource struct {
	Path  string
	Index *agent.ClientLookupIndex
}

// NewJSONClientLookupSource loads and indexes one explicit JSON file.
func NewJSONClientLookupSource(path string) (*JSONClientLookupSource, error) {
	payload, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("unable to load client lookup %s: %w", path, err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		return nil, fmt.Errorf("unable to load client lookup %s: %w", path, err)
	}
	return &JSONClientLookupSource{
		Path: path, Index: agent.NewClientLookupIndex(decoded),
	}, nil
}

// Lookup returns indexed records without network access.
func (s *JSONClientLookupSource) Lookup(
	_ context.Context,
	identifier agent.Identifier,
) ([]map[string]any, error) {
	return s.Index.Lookup(identifier), nil
}

// AliasCandidates returns deterministic acronym candidates.
func (s *JSONClientLookupSource) AliasCandidates(
	_ context.Context,
	alias string,
) ([]map[string]any, error) {
	return s.Index.AliasCandidates(alias), nil
}

// IndexedSource short-circuits unique local identities before remote calls.
type IndexedSource struct {
	Primary  agent.Source
	Fallback *JSONClientLookupSource
}

// Lookup returns a unique local result or queries the live provider.
func (s IndexedSource) Lookup(
	ctx context.Context,
	identifier agent.Identifier,
) ([]map[string]any, error) {
	indexed := s.Fallback.Index.Lookup(identifier)
	if len(indexed) == 1 {
		return indexed, nil
	}
	records, err := s.Primary.Lookup(ctx, identifier)
	if err != nil {
		return nil, err
	}
	if len(records) > 0 {
		return records, nil
	}
	return indexed, nil
}

// LookupBatch batches only identifiers not uniquely resolved locally.
func (s IndexedSource) LookupBatch(
	ctx context.Context,
	identifiers []agent.Identifier,
) ([][]map[string]any, error) {
	results := make([][]map[string]any, len(identifiers))
	unresolved := make([]agent.Identifier, 0)
	positions := make([]int, 0)
	for index, identifier := range identifiers {
		results[index] = s.Fallback.Index.Lookup(identifier)
		if len(results[index]) != 1 {
			unresolved = append(unresolved, identifier)
			positions = append(positions, index)
		}
	}
	if len(unresolved) == 0 {
		return results, nil
	}
	var remote [][]map[string]any
	var err error
	if batch, ok := s.Primary.(agent.BatchSource); ok {
		remote, err = batch.LookupBatch(ctx, unresolved)
	} else {
		remote = make([][]map[string]any, len(unresolved))
		for index, identifier := range unresolved {
			remote[index], err = s.Primary.Lookup(ctx, identifier)
			if err != nil {
				break
			}
		}
	}
	if err != nil {
		return nil, err
	}
	if len(remote) != len(unresolved) {
		return nil, fmt.Errorf("Resource Discovery batch returned an unexpected result count")
	}
	for index, records := range remote {
		if len(records) > 0 {
			results[positions[index]] = records
		}
	}
	return results, nil
}

// AliasCandidates returns local authoritative candidates.
func (s IndexedSource) AliasCandidates(
	ctx context.Context,
	alias string,
) ([]map[string]any, error) {
	return s.Fallback.AliasCandidates(ctx, alias)
}

// LookupLocal returns exact local matches without network access.
func (s IndexedSource) LookupLocal(
	ctx context.Context,
	identifier agent.Identifier,
) ([]map[string]any, error) {
	return s.Fallback.Lookup(ctx, identifier)
}
