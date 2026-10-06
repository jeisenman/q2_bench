package resourcediscovery

import (
	"context"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/agentmemory"
	"github.com/jeisenman/q2_bench/domain"
)

const clientUUID = "1f06da19-2f61-401c-a1b7-38902e4f3543"

type fakeSource struct {
	records     []map[string]any
	identifiers []Identifier
}

func (s *fakeSource) Lookup(
	_ context.Context,
	identifier Identifier,
) ([]map[string]any, error) {
	s.identifiers = append(s.identifiers, identifier)
	return cloneRecords(s.records), nil
}

func uniqueRecord() map[string]any {
	return map[string]any{
		"client_name": "Example Bank", "client_id": "client-123",
		"provisioned_client_id": "provisioned-123", "environment": "production",
		"prod_support_ignore": true, "client_secret": "do-not-print-client-secret",
	}
}

func explicitRequest(value string) domain.AgentRequest {
	return domain.AgentRequest{
		Prompt: "Resolve this identifier.", CorrelationID: "resource-discovery-test",
		Attributes: domain.Attributes{
			{Name: "identifier_kind", Value: "client_id"},
			{Name: "identifier_value", Value: value},
		},
	}
}

func TestAgentReportsUniqueSafeMatch(t *testing.T) {
	t.Parallel()
	source := &fakeSource{records: []map[string]any{uniqueRecord()}}
	result, err := (Agent{Source: source}).Run(
		context.Background(),
		explicitRequest(clientUUID),
	)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(result.Output, "Finding: unique match") ||
		!strings.Contains(result.Output, "Example Bank") ||
		strings.Contains(result.Output, "client_secret") {
		t.Fatalf("output = %q", result.Output)
	}
}

func TestAgentSortsAmbiguousMatches(t *testing.T) {
	t.Parallel()
	source := &fakeSource{records: []map[string]any{
		{"client_name": "Zulu Bank", "client_id": "z"},
		{"client_name": "Alpha Bank", "client_id": "a"},
	}}
	result, err := (Agent{Source: source}).Run(
		context.Background(),
		explicitRequest(clientUUID),
	)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Index(result.Output, "Alpha Bank") > strings.Index(result.Output, "Zulu Bank") {
		t.Fatalf("output is not sorted: %q", result.Output)
	}
}

func TestAgentRejectsShortClientIDBeforeLookup(t *testing.T) {
	t.Parallel()
	source := &fakeSource{}
	_, err := (Agent{Source: source}).Run(context.Background(), explicitRequest("1f0"))
	if err == nil || !strings.Contains(err.Error(), "complete UUID") {
		t.Fatalf("error = %v", err)
	}
	if len(source.identifiers) != 0 {
		t.Fatalf("source was called: %#v", source.identifiers)
	}
}

type indexedSource struct {
	index *ClientLookupIndex
}

func (s indexedSource) Lookup(_ context.Context, identifier Identifier) ([]map[string]any, error) {
	return s.index.Lookup(identifier), nil
}

func (s indexedSource) LookupLocal(
	_ context.Context,
	identifier Identifier,
) ([]map[string]any, error) {
	return s.index.Lookup(identifier), nil
}

func (s indexedSource) AliasCandidates(
	_ context.Context,
	alias string,
) ([]map[string]any, error) {
	return s.index.AliasCandidates(alias), nil
}

func TestAliasConfirmationAndResolution(t *testing.T) {
	t.Parallel()
	const canonicalID = "11111111-1111-4111-8111-111111111111"
	index := NewClientLookupIndex(map[string]any{
		canonicalID: map[string]any{
			"name": "City National Bank", "source": "resource-discovery-api",
			"api_status": "unique-match",
		},
	})
	memory, err := agentmemory.New(
		agentmemory.NewMemoryStore(),
		"resource-discovery",
		agentmemory.Scope{TenantID: "q2", Type: agentmemory.TeamScope, ID: "data-engineering"},
		3,
	)
	if err != nil {
		t.Fatal(err)
	}
	agent := Agent{Source: indexedSource{index: index}, Memory: memory}
	proposed, err := agent.Run(context.Background(), domain.AgentRequest{
		Prompt: "find CNB?", CorrelationID: "lookup",
	})
	if err != nil {
		t.Fatal(err)
	}
	memoryID := attributeString(proposed.Attributes, "memory_id")
	for index := 0; index < 3; index++ {
		_, err = agent.Run(context.Background(), domain.AgentRequest{
			Prompt: "Confirm the proposed alias.", CorrelationID: string(rune('a' + index)),
			Attributes: domain.Attributes{
				{Name: "memory_id", Value: memoryID},
				{Name: "memory_outcome", Value: "confirmed"},
			},
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	resolved, err := agent.Run(context.Background(), domain.AgentRequest{
		Prompt: "find CNB?", CorrelationID: "resolved",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(resolved.Output, canonicalID) {
		t.Fatalf("output = %q", resolved.Output)
	}
}

func TestClientNameParsing(t *testing.T) {
	t.Parallel()
	if got := ParseClientName("  Scotiabank - Data Validation "); got != "Scotiabank DV" {
		t.Fatalf("ParseClientName() = %q", got)
	}
	if got := ParseClientName("BoFA"); got != "Bank of America" {
		t.Fatalf("ParseClientName() = %q", got)
	}
}

func attributeString(attributes domain.Attributes, name string) string {
	for _, attribute := range attributes {
		if attribute.Name == name {
			return attribute.Value.(string)
		}
	}
	return ""
}
