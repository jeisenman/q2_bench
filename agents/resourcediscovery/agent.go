package resourcediscovery

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/agentmemory"
	"github.com/jeisenman/q2_bench/domain"
)

// Source reads non-secret resource metadata.
type Source interface {
	Lookup(context.Context, Identifier) ([]map[string]any, error)
}

// BatchSource resolves several identifiers through one provider operation.
type BatchSource interface {
	LookupBatch(context.Context, []Identifier) ([][]map[string]any, error)
}

// AliasCandidateSource finds canonical candidates for an unconfirmed alias.
type AliasCandidateSource interface {
	AliasCandidates(context.Context, string) ([]map[string]any, error)
}

// LocalLookupSource exposes a network-free authoritative lookup tier.
type LocalLookupSource interface {
	LookupLocal(context.Context, Identifier) ([]map[string]any, error)
}

// Agent searches injected metadata without write effects.
type Agent struct {
	Source Source
	Memory *agentmemory.Memory
}

// Definition returns the current version-two agent contract.
func (a Agent) Definition() domain.AgentDefinition {
	return domain.AgentDefinition{
		Name: "resource-discovery", Version: "2",
		Description:  "Resolve resources through local identity data and scoped memory.",
		Instructions: "Return only allowlisted metadata; never infer ambiguous clients.",
		Tools: []domain.ToolDefinition{{
			Name:        "ResourceDiscovery",
			Description: "Resolve safe resource metadata and confirmed aliases.",
		}},
	}
}

// Search validates, sanitizes, and orders source matches.
func (a Agent) Search(ctx context.Context, identifier Identifier) (Search, error) {
	if a.Source == nil {
		return Search{}, fmt.Errorf("source must implement ResourceDiscoverySource")
	}
	if err := identifier.Validate(); err != nil {
		return Search{}, err
	}
	records, err := a.Source.Lookup(ctx, identifier)
	if err != nil {
		return Search{}, err
	}
	return searchFromRecords(identifier, records)
}

// SearchBatch resolves identifiers through one provider batch when available.
func (a Agent) SearchBatch(
	ctx context.Context,
	identifiers []Identifier,
) ([]Search, error) {
	if len(identifiers) == 0 {
		return nil, nil
	}
	var records [][]map[string]any
	var err error
	if batch, ok := a.Source.(BatchSource); ok {
		records, err = batch.LookupBatch(ctx, identifiers)
	} else {
		records = make([][]map[string]any, len(identifiers))
		for index, identifier := range identifiers {
			records[index], err = a.Source.Lookup(ctx, identifier)
			if err != nil {
				break
			}
		}
	}
	if err != nil {
		return nil, err
	}
	if len(records) != len(identifiers) {
		return nil, fmt.Errorf("Resource Discovery batch returned an unexpected result count")
	}
	searches := make([]Search, len(identifiers))
	for index := range identifiers {
		searches[index], err = searchFromRecords(identifiers[index], records[index])
		if err != nil {
			return nil, err
		}
	}
	return searches, nil
}

// RunBatch resolves an ordered request slice before downstream reporting.
func (a Agent) RunBatch(
	ctx context.Context,
	requests []domain.AgentRequest,
) ([]domain.AgentResult, error) {
	identifiers := make([]Identifier, len(requests))
	for index, request := range requests {
		values, err := requestValues(request)
		if err != nil {
			return nil, fmt.Errorf("invalid batch identifier: %w", err)
		}
		identifiers[index], err = requestIdentifier(request, values)
		if err != nil {
			return nil, fmt.Errorf("invalid batch identifier: %w", err)
		}
	}
	searches, err := a.SearchBatch(ctx, identifiers)
	if err != nil {
		return nil, err
	}
	results := make([]domain.AgentResult, len(searches))
	for index, search := range searches {
		results[index] = searchResult(search, requests[index].CorrelationID, nil)
	}
	return results, nil
}

// Run executes one structured safe resource search.
func (a Agent) Run(
	ctx context.Context,
	request domain.AgentRequest,
) (domain.AgentResult, error) {
	if err := request.Validate(); err != nil {
		return domain.AgentResult{}, err
	}
	values, err := requestValues(request)
	if err != nil {
		return domain.AgentResult{}, fmt.Errorf("invalid identifier: %w", err)
	}
	feedback, err := parseMemoryFeedback(values)
	if err != nil {
		return domain.AgentResult{}, fmt.Errorf("invalid identifier: %w", err)
	}
	if feedback != nil {
		return a.recordFeedback(ctx, request, *feedback)
	}
	identifier, err := requestIdentifier(request, values)
	if err != nil {
		return domain.AgentResult{}, fmt.Errorf("invalid identifier: %w", err)
	}
	if identifier.Kind == ClientName && a.Memory != nil {
		if local, ok := a.Source.(LocalLookupSource); ok {
			records, lookupErr := local.LookupLocal(ctx, identifier)
			if lookupErr != nil {
				return domain.AgentResult{}, lookupErr
			}
			search, searchErr := searchFromRecords(identifier, records)
			if searchErr != nil {
				return domain.AgentResult{}, searchErr
			}
			if search.Status() == Unique {
				return searchResult(search, request.CorrelationID, nil), nil
			}
		}
		result, resolved, resolveErr := a.resolveMemory(ctx, request, identifier)
		if resolveErr != nil {
			return domain.AgentResult{}, resolveErr
		}
		if resolved {
			return result, nil
		}
	}
	search, err := a.Search(ctx, identifier)
	if err != nil {
		return domain.AgentResult{}, fmt.Errorf("%w", err)
	}
	return searchResult(search, request.CorrelationID, nil), nil
}

func (a Agent) resolveMemory(
	ctx context.Context,
	request domain.AgentRequest,
	identifier Identifier,
) (domain.AgentResult, bool, error) {
	resolution, err := a.Memory.ResolveAlias(ctx, identifier.Value)
	if err != nil {
		return domain.AgentResult{}, false, err
	}
	switch resolution.Status {
	case agentmemory.AliasResolved:
		memory, ok := resolution.Unique()
		if !ok {
			return domain.AgentResult{}, false, fmt.Errorf("resolved alias was not unique")
		}
		canonicalID := memoryMetadata(memory)["canonical_entity_id"]
		if canonicalID == "" {
			return domain.AgentResult{}, false, fmt.Errorf(
				"alias memory %s has no canonical ID",
				memory.ID,
			)
		}
		search, searchErr := a.Search(ctx, Identifier{Kind: ClientID, Value: canonicalID})
		if searchErr != nil {
			return domain.AgentResult{}, false, searchErr
		}
		return searchResult(search, request.CorrelationID, domain.Attributes{
			{Name: "memory_resolution", Value: "confirmed"},
		}), true, nil
	case agentmemory.AliasConfirmationRequired:
		memory, ok := resolution.Unique()
		if !ok {
			return domain.AgentResult{}, false, fmt.Errorf("proposed alias was not unique")
		}
		return confirmationResult(memory, request.CorrelationID), true, nil
	case agentmemory.AliasAmbiguous:
		return domain.AgentResult{}, false, fmt.Errorf(
			"alias %q has conflicting active memories",
			identifier.Value,
		)
	}
	candidates, ok := a.Source.(AliasCandidateSource)
	if !ok {
		return domain.AgentResult{}, false, nil
	}
	records, err := candidates.AliasCandidates(ctx, identifier.Value)
	if err != nil {
		return domain.AgentResult{}, false, err
	}
	if len(records) != 1 {
		return domain.AgentResult{}, false, nil
	}
	candidate, err := MetadataFromRecord(records[0])
	if err != nil || candidate.ClientName == "" || candidate.ProvisionedClientID == "" {
		return domain.AgentResult{}, false, err
	}
	memory, err := a.Memory.ProposeAlias(
		ctx,
		identifier.Value,
		"resource-discovery-client",
		candidate.ProvisionedClientID,
		candidate.ClientName,
	)
	if err != nil {
		return domain.AgentResult{}, false, err
	}
	return confirmationResult(memory, request.CorrelationID), true, nil
}

func (a Agent) recordFeedback(
	ctx context.Context,
	request domain.AgentRequest,
	feedback memoryFeedback,
) (domain.AgentResult, error) {
	if a.Memory == nil {
		return domain.AgentResult{}, fmt.Errorf("resource discovery memory is not configured")
	}
	memory, err := a.Memory.RecordAliasEvidence(
		ctx,
		feedback.ID,
		feedback.Outcome,
		request.CorrelationID,
	)
	if err != nil {
		return domain.AgentResult{}, err
	}
	return domain.AgentResult{
		Output:        feedbackOutput(memory, feedback.Outcome, a.Memory.AliasConfirmations),
		CorrelationID: request.CorrelationID,
		ToolCalls:     []string{"ResourceDiscovery"},
		Attributes: domain.Attributes{
			{Name: "memory_id", Value: memory.ID},
			{Name: "memory_status", Value: string(memory.Status)},
			{Name: "memory_evidence_count", Value: memory.EvidenceCount},
		},
	}, nil
}

func searchFromRecords(identifier Identifier, records []map[string]any) (Search, error) {
	matches := make([]Metadata, len(records))
	for index, record := range records {
		metadata, err := MetadataFromRecord(record)
		if err != nil {
			return Search{}, fmt.Errorf("invalid resource metadata: %w", err)
		}
		matches[index] = metadata
	}
	sort.Slice(matches, func(left, right int) bool {
		return metadataSortKey(matches[left]) < metadataSortKey(matches[right])
	})
	return Search{Identifier: identifier, Matches: matches}, nil
}

func metadataSortKey(metadata Metadata) string {
	values := []string{
		metadata.ClientName, metadata.ProvisionedClientID, metadata.ClientID,
		metadata.ResourceID, metadata.ResourceName, metadata.ResourceType,
		metadata.Subdomain, metadata.Environment, metadata.Zone, metadata.Service,
		metadata.ResourceSet, metadata.Database, metadata.Storage, metadata.DataLake,
		metadata.ReviewedProductionResendURL, metadata.RoutingSource,
		fmt.Sprint(metadata.ProdSupportIgnore),
	}
	return strings.Join(values, "\x00")
}
